#!/usr/bin/env python
import os
import webbrowser
import builtins
from contextlib import contextmanager
import io
from contextlib import redirect_stdout
try:
    from experta import *
except Exception:
    pass

EXPERTA_AVAILABLE = all(
    name in globals()
    for name in ("KnowledgeEngine", "Fact", "Rule", "AND", "OR", "DefFacts")
)

_ACTIVE_IO = None


class NeedInput(Exception):
    """Raised in web mode when the engine needs the next user response."""

    def __init__(self, question):
        super().__init__(question["prompt"])
        self.question = question


class DiagnosisComplete(Exception):
    """Raised in web mode when the engine reaches a diagnosis."""

    def __init__(self, disease, symptoms):
        super().__init__(disease)
        self.disease = disease
        self.symptoms = symptoms


def _prompt_id(kind, prompt, options=None):
    parts = [kind, prompt.strip()]
    if options:
        parts.extend(options)
    return "||".join(parts)


class EngineIOAdapter:
    """Feeds stored web answers back into the console expert engine."""

    def __init__(self, answers):
        self.answers = answers

    def _get_or_raise(self, question):
        key = question["key"]
        if key in self.answers:
            return self.answers[key]
        raise NeedInput(question)

    def text(self, prompt):
        prompt_clean = prompt.strip()

        if prompt_clean == "What's your name? :":
            question = {"key": "name", "type": "text", "prompt": prompt_clean, "question": "What's your name?"}
        elif prompt_clean == "what's your gender?(m/f) :":
            question = {
                "key": "gender",
                "type": "select",
                "prompt": prompt_clean,
                "question": "What's your gender?",
                "options": ["Male", "Female"],
            }
        elif prompt_clean == "Please list your drug allergies:":
            question = {"key": "allergy_details", "type": "text", "prompt": prompt_clean, "question": prompt_clean}
        elif prompt_clean == "Please list your current medications:":
            question = {"key": "medication_details", "type": "text", "prompt": prompt_clean, "question": prompt_clean}
        else:
            question = {
                "key": _prompt_id("text", prompt_clean),
                "type": "text",
                "prompt": prompt_clean,
                "question": prompt_clean,
            }

        value = self._get_or_raise(question)
        if question["key"] == "gender":
            return "m" if str(value).lower().startswith("m") else "f"
        return value

    def yes_no(self, prompt, key=None):
        prompt_clean = prompt.strip()
        question = {
            "key": key or _prompt_id("yesno", prompt_clean),
            "type": "yesno",
            "prompt": prompt_clean,
            "question": prompt_clean,
        }
        value = self._get_or_raise(question)
        return str(value).lower()

    def multi_input(self, prompt, options, key=None):
        prompt_clean = prompt.strip()
        question = {
            "key": key or _prompt_id("multi", prompt_clean, options),
            "type": "multi",
            "prompt": prompt_clean,
            "question": prompt_clean,
            "options": options + ["none"],
        }
        value = self._get_or_raise(question)
        if isinstance(value, list):
            selected = value
        else:
            selected = [value]
        return selected

    def diagnose(self, disease, symptoms):
        raise DiagnosisComplete(disease, symptoms)


@contextmanager
def engine_io_context(adapter):
    global _ACTIVE_IO
    previous_io = _ACTIVE_IO
    previous_input = builtins.input
    _ACTIVE_IO = adapter
    builtins.input = adapter.text
    try:
        yield
    finally:
        _ACTIVE_IO = previous_io
        builtins.input = previous_input

### Helper functions ###

def multi_input(input_str, options=[]):
    if _ACTIVE_IO is not None:
        return _ACTIVE_IO.multi_input(input_str, options)

    print(input_str)

    while True:
        try:
            all_options = options + ["none"]

            print("0) none")
            for i, option in enumerate(options):
                print(f"{i+1}) {option}")

            choice = input("Your choice: ").split()

            indexes = [int(x)-1 for x in choice]

            for x in indexes:
                if x >= len(all_options):
                    raise ValueError

                if x == -1 and len(indexes) > 1:
                    raise ValueError

            return [all_options[i] for i in indexes]

        except:
            print("Invalid input. Try again.")

def yes_no(input_str):
    if _ACTIVE_IO is not None:
        return _ACTIVE_IO.yes_no(input_str)

    input_str += " (yes/no): "

    while True:
        try:
            user_input = input(input_str).strip().lower()

            if user_input in ["y", "yes", "yup"]:
                return "yes"

            elif user_input in ["n", "no", "nope"]:
                return "no"

            else:
                print("Please answer only yes or no.")

        except KeyboardInterrupt:
            print("\nPlease do not press Ctrl+C. Type yes or no.")

        except EOFError:
            print("\nInput error. Please try again.")

def suggest_disease(disease, symptoms):
    if _ACTIVE_IO is not None:
        _ACTIVE_IO.diagnose(disease, symptoms)

    print(f"\nYou might be suffering from {disease}")

    symptoms_text = '- ' + '\n - '.join(symptoms)

    print(f"This conclusion is reached because you show symptoms among the following:\n{symptoms_text}")

    open_doc = yes_no(f"\nDo you want to know more regarding {disease}?")

    if open_doc == "yes":
        html_file = os.path.join(os.getcwd(), "Treatment", "html", f"{disease}.html")

        if os.path.exists(html_file):
            webbrowser.open(f"file:///{html_file}", new=2)
        else:
            print(f"HTML file for {disease} not found.")

    raise SystemExit


def diagnose_from_answers(answers):
    """Pure diagnosis helper shared by the web app and console expert system."""
    a = answers
    no_fever = a.get("fever_type") == "No Fever"
    normal_fever = a.get("fever_type") == "Normal Fever"
    low_fever = a.get("fever_type") == "Low Fever"
    high_fever = a.get("fever_type") == "High Fever"

    def yes_count(*keys):
        return sum(1 for key in keys if a.get(key) == "yes")

    if a.get("red_eyes") == "yes":
        if a.get("eye_crusting") == "yes" or a.get("eye_burn") == "yes":
            return "Conjunctivitis", ["Red eyes", "Burning/crusting in eyes", "Eye discomfort"]
        if a.get("eye_irritation") == "yes":
            return "Eye Allergy", ["Red eyes", "Eye irritation", "Allergic reaction"]

    if (
        a.get("diabetes") == "yes"
        and a.get("fatigue") == "yes"
        and a.get("extreme_thirst") == "yes"
        and a.get("extreme_hunger") == "yes"
        and yes_count(
            "frequent_urination", "weight_loss", "irritability",
            "blurred_vision", "frequent_infections", "slow_healing_sores"
        ) >= 3
    ):
        return "Diabetes", [
            "Fatigue", "Extreme thirst", "Extreme hunger", "Weight loss",
            "Blurred vision", "Frequent infections", "Frequent urination",
            "Irritability", "Slow healing of sores"
        ]

    if (
        a.get("hypertension") == "yes"
        and a.get("short_breath") == "yes"
        and a.get("chest_pain") == "yes"
        and yes_count("heaviness", "sweating", "dizziness", "burning_heart") >= 2
    ):
        return "Coronary Arteriosclerosis", [
            "Shortness of breath", "Chest pain", "Heaviness",
            "Sweating", "Dizziness", "Burning sensation near heart"
        ]

    if (
        a.get("heart_disease") == "yes"
        and a.get("fatigue") == "yes"
        and a.get("short_breath") == "yes"
        and yes_count(
            "irregular_heartbeat", "weakness", "pale_skin",
            "lightheadedness", "cold_limbs"
        ) >= 3
    ):
        return "Anemia", [
            "Shortness of breath", "Fatigue", "Irregular heartbeat",
            "Weakness", "Pale skin", "Dizziness", "Cold limbs"
        ]

    if (
        a.get("thyroid") == "yes"
        and a.get("fatigue") == "yes"
        and yes_count(
            "depression", "constipation", "feeling_cold", "dry_skin",
            "dry_hair", "weight_gain", "decreased_sweating",
            "slow_heart_rate", "joint_stiffness", "hoarseness"
        ) >= 5
    ):
        return "Hypothyroidism", [
            "Fatigue", "Depression", "Constipation", "Cold feeling",
            "Dry skin", "Dry hair", "Weight gain", "Decreased sweating",
            "Slow heart rate", "Joint pains", "Hoarseness in voice"
        ]

    if high_fever and yes_count(
        "severe_headache", "eyes_pain", "muscle_pain",
        "severe_joint_pain", "nausea", "rashes", "bleeding"
    ) >= 5:
        return "Dengue", [
            "High fever", "Headache", "Eye pain", "Muscle pain",
            "Joint pains", "Nausea", "Rashes", "Bleeding"
        ]

    if low_fever and yes_count(
        "headache", "persistent_cough", "wheezing", "chills",
        "chest_tightness", "sore_throat", "body_aches",
        "breathlessness", "blocked_nose"
    ) >= 7:
        return "Bronchitis", [
            "Slight fever", "Cough", "Wheezing", "Chills",
            "Tightness in chest", "Sore throat", "Body aches",
            "Headache", "Breathlessness", "Blocked nose"
        ]

    if a.get("appetite_loss") == "yes" and no_fever and a.get("short_breath") != "yes" and a.get("fatigue") != "yes":
        if a.get("joint_pain") == "yes" and yes_count(
            "stiff_joint", "swell_joint", "red_skin_joint",
            "decreased_range", "tired_small_walk"
        ) >= 3:
            return "Arthritis", [
                "Stiff joints", "Swelling in joints", "Joint pains",
                "Red skin around joints", "Tiredness",
                "Reduced movement near joints", "Appetite loss"
            ]

        if a.get("vomit_type") == "Severe Vomiting" and yes_count(
            "burning_stomach", "bloating", "mild_nausea",
            "weight_loss", "abdominal_pain"
        ) >= 3:
            return "Peptic Ulcer", [
                "Appetite loss", "Severe vomiting",
                "Burning sensation in stomach", "Bloated stomach",
                "Nausea", "Weight loss", "Abdominal pain"
            ]

        if a.get("vomit_type") == "Normal Vomiting" and yes_count(
            "nausea", "fullness", "bloating",
            "abdominal_pain", "indigestion", "gnawing"
        ) >= 4:
            return "Gastritis", [
                "Appetite loss", "Vomiting", "Nausea",
                "Fullness near abdomen", "Bloating near abdomen",
                "Abdominal pain", "Indigestion", "Gnawing pain near abdomen"
            ]

    if a.get("fatigue") == "yes" and no_fever and a.get("short_breath") != "yes":
        if a.get("extreme_thirst") == "yes" and a.get("extreme_hunger") == "yes" and yes_count(
            "frequent_urination", "weight_loss", "irritability",
            "blurred_vision", "frequent_infections", "slow_healing_sores"
        ) >= 4:
            return "Diabetes", [
                "Fatigue", "Extreme thirst", "Extreme hunger", "Weight loss",
                "Blurred vision", "Frequent infections", "Frequent urination",
                "Irritability", "Slow healing of sores"
            ]

        if a.get("extreme_thirst") == "yes" and a.get("dizziness") == "yes" and yes_count(
            "less_frequent_urination", "dark_urine", "lethargy", "dry_mouth"
        ) >= 2:
            return "Dehydration", [
                "Fatigue", "Extreme thirst", "Dizziness", "Dark urine",
                "Lethargic feeling", "Dry mouth", "Less frequent urination"
            ]

        if a.get("muscle_weakness") == "yes" and yes_count(
            "depression", "constipation", "feeling_cold", "dry_skin",
            "dry_hair", "weight_gain", "decreased_sweating",
            "slow_heart_rate", "joint_stiffness", "hoarseness"
        ) >= 7:
            return "Hypothyroidism", [
                "Fatigue", "Muscle weakness", "Depression", "Constipation",
                "Cold feeling", "Dry skin", "Dry hair", "Weight gain",
                "Decreased sweating", "Slow heart rate", "Joint pains",
                "Hoarseness in voice"
            ]

    if a.get("short_breath") == "yes" and no_fever:
        if a.get("back_joint_pain") == "yes" and yes_count(
            "sweating", "snoring", "sudden_physical",
            "tired_small_walk", "isolated", "low_confidence"
        ) >= 4:
            return "Obesity", [
                "Shortness of breath", "Back and joint pains",
                "High sweating", "Snoring habit", "Tiredness",
                "Low confidence"
            ]

        if (
            a.get("chest_pain") == "yes"
            and a.get("fatigue") == "yes"
            and a.get("headache") == "yes"
            and yes_count(
                "irregular_heartbeat", "weakness", "pale_skin",
                "lightheadedness", "cold_limbs"
            ) >= 3
        ):
            return "Anemia", [
                "Shortness of breath", "Chest pain", "Fatigue",
                "Headache", "Irregular heartbeat", "Weakness",
                "Pale skin", "Dizziness", "Cold limbs"
            ]

        if (
            a.get("chest_pain") == "yes"
            and a.get("fatigue") == "yes"
            and a.get("pain_arms") == "yes"
            and yes_count("heaviness", "sweating", "dizziness", "burning_heart") >= 2
        ):
            return "Coronary Arteriosclerosis", [
                "Shortness of breath", "Chest pain", "Fatigue",
                "Arm pains", "Heaviness", "Sweating",
                "Dizziness", "Burning sensation near heart"
            ]

        if (
            a.get("chest_pain") == "yes"
            and a.get("cough") == "yes"
            and yes_count("wheezing", "sleep_trouble") >= 1
        ):
            return "Asthma", [
                "Shortness of breath", "Chest pain", "Cough",
                "Wheezing sound when exhaling",
                "Trouble sleeping because of coughing or wheezing"
            ]

    if normal_fever:
        if (
            a.get("nf_chest_pain") == "yes"
            and a.get("fatigue") == "yes"
            and a.get("chills") == "yes"
            and yes_count("persistent_cough", "weight_loss", "night_sweats", "cough_blood") >= 2
        ):
            return "Tuberculosis", [
                "Fever", "Chest pain", "Fatigue", "Loss of appetite", "Persistent cough"
            ]

        if (
            a.get("fatigue") == "yes"
            and a.get("sore_throat") == "yes"
            and yes_count(
                "weakness", "dry_cough", "muscle_ache",
                "chills", "nasal_congestion", "headache"
            ) >= 4
        ):
            return "Influenza", [
                "Fever", "Fatigue", "Sore throat", "Weakness",
                "Dry cough", "Muscle aches", "Chills",
                "Nasal congestion", "Headache"
            ]

        if (
            a.get("fatigue") == "yes"
            and a.get("abdominal_pain") == "yes"
            and yes_count("flu_like", "dark_urine", "pale_stool", "weight_loss", "jaundice") >= 3
        ):
            return "Hepatitis", [
                "Fever", "Fatigue", "Abdominal pain", "Flu-like symptoms",
                "Dark urine", "Pale stool", "Weight loss",
                "Yellow eyes and skin (jaundice)"
            ]

        if (
            a.get("nf_chest_pain") == "yes"
            and a.get("short_breath") == "yes"
            and a.get("nausea") == "yes"
            and yes_count("short_breath", "high_sweat", "rapid_breath", "cough_phlegm", "diarrhea") >= 3
        ):
            return "Pneumonia", [
                "Fever", "Chest pain", "Shortness of breath", "Nausea",
                "Sweating with chills", "Rapid breathing",
                "Cough with phlegm", "Diarrhea"
            ]

        if (
            a.get("chills") == "yes"
            and a.get("abdominal_pain") == "yes"
            and a.get("nausea") == "yes"
            and yes_count("headache", "sweat", "cough", "weakness", "muscle_ache", "back_pain") >= 4
        ):
            return "Malaria", [
                "Fever", "Chills", "Abdominal pain", "Nausea",
                "Headache", "Sweating", "Cough", "Weakness",
                "Muscle pain", "Back pain"
            ]

        if a.get("rashes") == "yes" and yes_count(
            "headache", "muscle_ache", "sore_throat", "lymph",
            "diarrhea", "cough", "weight_loss", "night_sweats"
        ) >= 6:
            return "AIDS", [
                "Fever", "Rashes", "Headache", "Muscle ache",
                "Sore throat", "Swollen lymph nodes", "Diarrhea",
                "Cough", "Weight loss", "Night sweat"
            ]

        if a.get("nausea") == "yes" and yes_count(
            "upper_abdominal_pain", "pain_after_eating",
            "heartbeat_fast", "weight_loss", "oily_stool"
        ) >= 3:
            return "Pancreatitis", [
                "Nausea", "Fever", "Upper abdominal pain",
                "Heartbeat", "Weight loss", "Oily and smelly stool"
            ]

        if (
            a.get("fatigue") == "yes"
            and a.get("short_breath") == "yes"
            and a.get("nausea") == "yes"
            and yes_count("chills", "cough", "body_aches", "headache", "sore_throat", "lose_smell", "diarrhea") >= 4
        ):
            return "Corona Virus", [
                "Fever", "Fatigue", "Shortness of breath", "Nausea",
                "Chills", "Cough", "Body aches", "Headache",
                "Sore throat", "Diarrhea", "Loss of taste/smell"
            ]

    return None, []


class DiagnosisFlow:
    """Web wrapper that replays the exact terminal engine to fetch the next question."""

    def __init__(self):
        self.answers = {}
        self.result = None
        self.current_question = None
        self.done = False
        self.history = []
        self.prediction_prompted = None

    def get_current_question(self):
        if self.done:
            return None

        if self.current_question is not None:
            return self.current_question

        if not EXPERTA_AVAILABLE:
            self.done = True
            self.result = {
                "disease": None,
                "symptoms": [],
                "error": "experta is required to run the exact terminal engine."
            }
            return None

        adapter = EngineIOAdapter(self.answers)
        engine = MedicalExpert()

        try:
            with engine_io_context(adapter), redirect_stdout(io.StringIO()):
                engine.reset()
                engine.run()
        except NeedInput as need:
            question = need.question
            if question["key"] == "gender":
                question = dict(question)
                question["type"] = "select"
                question["options"] = ["Male", "Female"]
            if not self.history or self.history[-1]["key"] != question["key"]:
                self.history.append(dict(question))
            self.current_question = question
            return question
        except DiagnosisComplete as result:
            self.result = {"disease": result.disease, "symptoms": result.symptoms}
            self.done = True
            return None

        self.result = {"disease": None, "symptoms": []}
        self.done = True
        return None

    def submit_answer(self, key, answer):
        self.answers[key] = answer
        self.current_question = None
        self.result = None
        self.done = False

    def run_diagnosis(self):
        if self.result:
            return self.result.get("disease"), self.result.get("symptoms", [])

        adapter = EngineIOAdapter(self.answers)
        engine = MedicalExpert()

        try:
            with engine_io_context(adapter), redirect_stdout(io.StringIO()):
                engine.reset()
                engine.run()
        except DiagnosisComplete as result:
            self.result = {"disease": result.disease, "symptoms": result.symptoms}
            return result.disease, result.symptoms
        except NeedInput:
            return None, []

        self.result = {"disease": None, "symptoms": []}
        return None, []

    def start_edit(self, key):
        if key not in self.answers:
            return

        keep_keys = []
        trimmed_history = []

        for question in self.history:
            trimmed_history.append(question)
            keep_keys.append(question["key"])
            if question["key"] == key:
                break

        self.history = trimmed_history
        self.answers = {k: self.answers[k] for k in keep_keys if k in self.answers}
        self.current_question = None
        self.result = None
        self.done = False
        self.prediction_prompted = None

    def revise_answer(self, key, answer):
        self.start_edit(key)
        self.answers[key] = answer
        self.current_question = None
        self.result = None
        self.done = False


# ============================================================
# HTML TEMPLATES
# ============================================================

if EXPERTA_AVAILABLE:
    class MedicalExpert(KnowledgeEngine):
    
        @DefFacts()
        def _initial_action_(self):
            print("Hi. I am an Expert System who can help you in medical diagnosis.")
            print("When prompted with options, enter space seperated integer values corresponding to all the options which apply to you.")
            print("Please answer the following questions to find out the disease and its cure")
            # yeild all the facts you require here
            yield Fact(action="engine_start")
            
        @Rule(Fact(action="engine_start"))
        def getUserInfo(self):
            self.declare(Fact(name=input("What's your name? : ")))
            self.declare(Fact(gender=input("what's your gender?(m/f) : ")))
            self.declare(Fact(action="medical_history"))
    
        @Rule(Fact(action="medical_history"))
        def askMedicalHistory(self):
            print("\n" + "="*60)
            print("Now let me ask about your medical history.")
            print("This information helps me provide better diagnosis.")
            print("="*60)
    
            diabetes = yes_no("Do you have Diabetes?")
            if diabetes == "yes":
                self.declare(Fact(diabetes="yes"))
                diabetes_type = multi_input("What type of diabetes?", ["Type 1", "Type 2", "Gestational", "Don't know"])
                if diabetes_type[0] != "none":
                    diabetes_type_clean = diabetes_type[0].replace(" ", "_").replace(",", "")
                    self.declare(Fact(diabetes_type=diabetes_type_clean))
            else:
                self.declare(Fact(diabetes="no"))
    
            blood_pressure = yes_no("Do you have High Blood Pressure (Hypertension)?")
            if blood_pressure == "yes":
                self.declare(Fact(hypertension="yes"))
                bp_managed = yes_no("Is it managed with medication?")
                self.declare(Fact(hypertension_managed=bp_managed))
            else:
                self.declare(Fact(hypertension="no"))
    
            heart_disease = yes_no("Do you have any Heart Disease?")
            if heart_disease == "yes":
                self.declare(Fact(heart_disease="yes"))
                heart_condition = multi_input("What type of heart condition?", ["Coronary Artery Disease", "Heart Failure", "Arrhythmia", "Heart Valve Problem", "Other"])
                if heart_condition[0] != "none":
                    heart_condition_clean = heart_condition[0].replace(" ", "_").replace(",", "")
                    self.declare(Fact(heart_condition_type=heart_condition_clean))
            else:
                self.declare(Fact(heart_disease="no"))
    
            asthma_history = yes_no("Do you have Asthma?")
            self.declare(Fact(asthma=asthma_history))
    
            kidney_disease = yes_no("Do you have Kidney Disease?")
            self.declare(Fact(kidney_disease=kidney_disease))
    
            liver_disease = yes_no("Do you have Liver Disease?")
            self.declare(Fact(liver_disease=liver_disease))
    
            thyroid = yes_no("Do you have Thyroid Disorder?")
            if thyroid == "yes":
                self.declare(Fact(thyroid_disorder="yes"))
                thyroid_type = multi_input("What type?", ["Hyperthyroidism", "Hypothyroidism", "Don't know"])
                if thyroid_type[0] != "none":
                    thyroid_type_clean = thyroid_type[0].replace(" ", "_").replace(",", "")
                    self.declare(Fact(thyroid_type=thyroid_type_clean))
            else:
                self.declare(Fact(thyroid_disorder="no"))
    
            cancer_history = yes_no("Do you have or had Cancer?")
            if cancer_history == "yes":
                self.declare(Fact(cancer_history="yes"))
                cancer_type = multi_input("What type (if known)?", ["Blood", "Lung", "Breast", "Colon", "Prostate", "Other", "Don't know"])
                if cancer_type[0] != "none":
                    cancer_type_clean = cancer_type[0].replace(" ", "_").replace(",", "")
                    self.declare(Fact(cancer_type=cancer_type_clean))
            else:
                self.declare(Fact(cancer_history="no"))
    
            # Allergies
            allergies = yes_no("Do you have any known drug allergies?")
            if allergies == "yes":
                self.declare(Fact(drug_allergies="yes"))
                allergy_details = input("Please list your drug allergies: ")
                if allergy_details.strip():
                    self.declare(Fact(allergy_details=allergy_details))
            else:
                self.declare(Fact(drug_allergies="no"))
    
            # Current medications
            meds = yes_no("Are you currently taking any medications?")
            if meds == "yes":
                self.declare(Fact(current_medications="yes"))
                med_details = input("Please list your current medications: ")
                if med_details.strip():
                    self.declare(Fact(medication_details=med_details))
            else:
                self.declare(Fact(current_medications="no"))
    
            self.declare(Fact(action="questionnaire"))
        
        @Rule(Fact(action="questionnaire"))
        def askBasicQuestions(self):
            self.declare(Fact(red_eyes=yes_no("Do you suffer from red eyes?")))
            self.declare(Fact(fatigue=yes_no("Are you suffering from fatigue?")))
            self.declare(Fact(short_breath=yes_no("Are you having shortness of breath?")))
            self.declare(Fact(appetite_loss=yes_no("Are you having loss of appetite?")))
            fevers = multi_input("Do you suffer from fever?",["Normal Fever","Low Fever","High Fever"])
            if fevers[0]!="none":
                self.declare(Fact(fever="yes"))
                for f in fevers:
                    f=f.replace(" ","_")
                    self.declare(Fact(f)) 
            else:
                self.declare(Fact(fever="no"))
    
        @Rule(AND(Fact(appetite_loss="yes"), Fact(fever="no"), Fact(short_breath="no"), Fact(fatigue="no")))
        def askRelatedToAppetiteLoss(self):
            self.declare(Fact(joint_pain=yes_no("Are you having any joint pains?")))
            vomits = multi_input("Did you have vomitings?",["Severe Vomiting", "Normal Vomiting"])
            if vomits[0]!="none":
                self.declare(Fact(vomit="yes"))
                for v in vomits:
                    v=v.replace(" ","_")
                    self.declare(Fact(v))
            else:
                self.declare(Fact(vomit="no"))
    
        @Rule(AND(Fact(appetite_loss="yes"), Fact(fever="no"), Fact(short_breath="no"), Fact(fatigue="no"), Fact(joint_pain="yes")))
        def askArthritis(self):
            stiff_joint=yes_no("Are you having stiff Joints?")
            swell_joint=yes_no("Are you experiencing swelly Joints?")
            red_skin_around_joint=yes_no("Did the skin turn red around the Joints?")
            decreased_range=yes_no("Did the range of motion decrease at the Joints?")
            tired=yes_no("Are you feeling tired even if you walk small distance?")
            count=0
            for string in [stiff_joint, swell_joint, red_skin_around_joint, decreased_range, tired]:
                if string=="yes":
                    count+=1
    
            if count>=3:
                symptoms = ["Stiff joints", "Swelling in joints", "Joint Pains", "Red shik around joints", "Tiredness", "Reduced Movement near joints", "Appetite loss"]
                suggest_disease("Arthritis", symptoms)
    
        @Rule(AND(Fact(appetite_loss="yes"), Fact(fever="no"), Fact(short_breath="no"), Fact(fatigue="no"), Fact("Severe_Vomiting")))
        def askPepticUlcer(self):
            burning_stomach=yes_no("Is your stomach has burning sensation?")
            bloating=yes_no("Are you having a feeling of fullness, bloating or belching?")
            mild_nausea=yes_no("Are you having mild Nausea?")
            weight_loss=yes_no("Did you lose your weight?")
            abdominal_pain=yes_no("Are you having an intense and localized abdominal pain?")
            count=0
            for string in [burning_stomach, bloating, mild_nausea, weight_loss, abdominal_pain]:
                if string=="yes":
                    count+=1
    
            if count>=3:
                symptoms = ["Appetite loss", "Severe Vomiting", "Burning sensation in stomach", "Bloated stomach", "Nausea", "Weight loss", "Abdominal pain"]
                suggest_disease("Peptic Ulcer", symptoms)
    
        @Rule(AND(Fact(appetite_loss="yes"), Fact(fever="no"), Fact(short_breath="no"), Fact(fatigue="no"), Fact("Normal_Vomiting")))
        def askGastritis(self):
            nausea=yes_no("Are you having a feeling of vomiting(Nausea)?")
            fullness=yes_no("Are you having a feeling of fullness in your upper abdomen?")
            bloating=yes_no("Are you feeling bloating in your abdomen?")
            abdominal_pain=yes_no("Are you having pain near abdomen?")
            indigestion=yes_no("Are you facing problems of indigestion?")
            gnawing=yes_no("Are you experiencing gnawing or burning ache or pain in your upper abdomen that may become either worse or better with eating")
            count=0
            for string in [nausea, fullness, bloating, abdominal_pain, indigestion, gnawing]:
                if string=="yes":
                    count+=1
    
            if count>=4:
                symptoms = ["Appetite loss", "Vomiting", "Nausea", "Fullness near abdomen", "Bloating near abdomen", "Abdominal pain", "Indigestion", "Gnawing pain near abdomen"]
                suggest_disease("Gastritis", symptoms)
    
    
        @Rule(AND(Fact(fatigue="yes"), Fact(fever="no"), Fact(short_breath="no")))
        def askRelatedToFatigue(self):
            self.declare(Fact(extreme_thirst=yes_no("Are you feeling extremely thirsty than before?")))
            self.declare(Fact(extreme_hunger=yes_no("Are you feeling extremely hungry than before?")))
            self.declare(Fact(dizziness=yes_no("Are you feeling dizzy?")))
            self.declare(Fact(muscle_weakness=yes_no("Are your muscles weaker than berfore?")))
    
        @Rule(AND(Fact(fatigue="yes"), Fact(fever="no"), Fact(short_breath="no"), Fact(extreme_thirst="yes"), Fact(extreme_hunger="yes")))
        def askDiabetes(self):
            frequent_urination=yes_no("Is your Urination more frequent than before?")
            weight_loss=yes_no("Did you lose your weight unintentionally?")
            irratabiliry=yes_no("Are you more irritable now a days?")
            blurred_vision=yes_no("Did your vision get blurred?")
            frequent_infections=yes_no("Are you having frequent infections such as gums or skin infections")
            sores=yes_no("Are your sores healing slowly?")
            count=0
            for string in [frequent_urination, weight_loss, irratabiliry, blurred_vision, frequent_infections, sores]:
                if string=="yes":
                    count+=1
    
            if count>=4:
                symptoms = ["Fatigue", "Extreme thirst", "Extreme hunger", "Weight loss", "Blurred vision", "Frequent infections", "Frequent urination", "Irritability", "Slow healing of sores"]
                suggest_disease("Diabetes", symptoms)
    
        @Rule(AND(Fact(fatigue="yes"), Fact(fever="no"), Fact(short_breath="no"), Fact(extreme_thirst="yes"), Fact(dizziness="yes")))
        def askDehydration(self):
            less_frequent_urination=yes_no("Are you having less frequent urination?")
            dark_urine=yes_no("Did the urine become dark?")
            lethargy=yes_no("Are you feeling lethargic?")
            dry_mouth=yes_no("Is your mouth considerably dry?")
            count=0
            for string in [less_frequent_urination, dark_urine, lethargy, dry_mouth]:
                if string=="yes":
                    count+=1
    
            if count>=2:
                symptoms = ["Fatigue", "Extreme thirst", "Dizziness", "Dark urine", "Lethargic feeling", "Dry mouth", "Less frequent urination"]
                suggest_disease("Dehydration", symptoms)
    
        @Rule(AND(Fact(fatigue="yes"), Fact(fever="no"), Fact(short_breath="no"), Fact(muscle_weakness="yes")))
        def askHypothoroidism(self):
            depression=yes_no("Are you feeling depressed now a days?")
            constipation=yes_no("Are you experiencing constipation?")
            feeling_cold=yes_no("Are you feeling cold?")
            dry_skin=yes_no("Has your skin became drier?")
            dry_hair=yes_no("Is your hair too becoming dry and also thinner?")
            weight_gain=yes_no("Did you gain your weight considerably?")
            decreased_sweating=yes_no("Are you not sweating much as earlier?")
            slowed_heartrate=yes_no("Did your heart rate slow down?")
            pain_joints=yes_no("Are you experiencing pain and stiffness in joints?")
            hoarseness=yes_no("Is your voice changing abnormally?")
            count=0
            for string in [depression, constipation, feeling_cold, dry_skin, dry_hair, weight_gain, decreased_sweating, slowed_heartrate, pain_joints, hoarseness]:
                if string=="yes":
                    count+=1
    
            if count>=7:
                symptoms = ["Fatigue", "Muscle weakness", "Depression", "Constipation", "Cold feeling", "Dry skin", "Dry hair", "Weight gain", "Decreased sweating", "Slow heart rate", "Joint pains", "Hoarseness in voice"]
                suggest_disease("Hypothyroidism", symptoms)
    
        @Rule(AND(Fact(short_breath="yes"), Fact(fever="no")))
        def askRelatedToShortBreath(self):
            self.declare(Fact(back_joint_pian=yes_no("Are you having back and joint pain?")))
            self.declare(Fact(chest_pain=yes_no("Are you having chest pain?")))
            self.declare(Fact(cough=yes_no("Are you having cough frequently?")))
            self.declare(Fact(fatigue=yes_no("Are you feeling fatigue?")))
            self.declare(Fact(headache=yes_no("Are you having headache?")))
            self.declare(Fact(pain_arms=yes_no("Are you having pain in arms and shoulders?")))
    
        @Rule(AND(Fact(short_breath="yes"), Fact(fever="no"), Fact(back_joint_pian="yes")))
        def askObesity(self):
            sweating=yes_no("Are you sweating more than normal?")
            snoring=yes_no("Did you develop a habit of snoring?")
            sudden_physical=yes_no("Are you not able to cope up with sudden physical activity?")
            tired=yes_no("Are you feeling tired every day withour doing much work?")
            isolatd=yes_no("Are you feeling isolated?")
            confidence=yes_no("Are you having low confidence and self esteem in day to day activities?")
            count=0
            for string in [sweating, snoring, sudden_physical, tired, isolatd, confidence]:
                if string=="yes":
                    count+=1
    
            if count>=4:
                symptoms = ["Shortness in breath", "Back and Joint pains", "High sweating", "Snoring habit", "Tireness", "Low confidence"]
                suggest_disease("Obesity", symptoms)
    
        @Rule(AND(Fact(short_breath="yes"), Fact(fever="no"), Fact(chest_pain="yes"), Fact(fatigue="yes"), Fact(headache="yes")))
        def askAnemia(self):
            irregular_heartbeat=yes_no("Are you experiencing irregular heartbeat?")
            weakness=yes_no("Are you feeling weak?")
            pale_skin=yes_no("Has your skin turned pale or yellowish?")
            lightheadedness=yes_no("Are you having dizziness or light headedness?")
            cold_hands_feet=yes_no("Are you having cold hands and feet?")
            count=0
            for string in [irregular_heartbeat, weakness, pale_skin, lightheadedness, cold_hands_feet]:
                if string=="yes":
                    count+=1
    
            if count>=3:
                symptoms = ["Shortness in breath", "Chest pain", "Fatigue", "Headache", "Irregular heartbeat", "Weakness", "Pale skin", "Dizziness", "Cold limbs"]
                suggest_disease("Anemia", symptoms)
    
        @Rule(AND(Fact(short_breath="yes"), Fact(fever="no"), Fact(chest_pain="yes"), Fact(fatigue="yes"), Fact(pain_arms="yes")))
        def askCAD(self):
            heaviness=yes_no("Did you have feeling of heaviness or tightness, usually in the centre of the chest, which may spread to the arms, neck, jaw, back or stomach?")
            sweating=yes_no("Are you sweating frequently?")
            dizziness=yes_no("Are you feeling dizzy?")
            burning=yes_no("Do you feel burning sensation near heart?")
            count=0
            for string in [heaviness, sweating, dizziness, burning]:
                if string=="yes":
                    count+=1
    
            if count>=2:
                symptoms = ["Shortness in breath", "Chest pain", "Fatigue", "Arm pains", "Heaviness", "Sweating", "Diziness", "Burning sensation near heart"]
                suggest_disease("Coronary Arteriosclerosis", symptoms)
    
        @Rule(AND(Fact(short_breath="yes"), Fact(fever="no"), Fact(chest_pain="yes"), Fact(cough="yes")))
        def askAsthma(self):
            Wheezing=yes_no("Are you having a whistling or wheezing sound when exhaling?")
            sleep_trouble=yes_no("Are you having trouble sleeping caused by shortness of breath, coughing or wheezing?")
            count=0
            for string in [Wheezing, sleep_trouble]:
                if string=="yes":
                    count+=1
    
            if count>=1:
                symptoms = ["Shortness in breath", "Chest pain", "Cough", "Wheezing sound when exhaling", "Trouble sleep because of coughing or wheezing"]
                suggest_disease("Asthma", symptoms)
    
        @Rule(Fact("High_Fever"))
        def askDengue(self):
            headache=yes_no("Are you experiencing severe headache?")
            eyes_pain=yes_no("Are you having pain behind eyes?")
            muscle_pain=yes_no("Are you having severe muscle pain?")
            joint_pian=yes_no("Are you having severe joint pain?")
            nausea=yes_no("Have you vomited or felt like vomiting(Nausea)?")
            rashes=yes_no("Have you experienced rashes on skin which appears two to five days after the onset of fever?")
            bleeding=yes_no("Are you having mild bleeding such a nose bleed, bleeding gums, or easy bruising?")
            count=0
            for string in [headache, eyes_pain, muscle_pain, joint_pian, nausea, rashes, bleeding]:
                if string=="yes":
                    count+=1
    
            if count>=5:
                symptoms = ["High fever", "Headache", "Eye pain", "Muscle pain", "Joint pains", "Nausea", "Rashes", "Bleeding"]
                suggest_disease("Dengue", symptoms)
    
        @Rule(Fact("Low_Fever"))
        def askBronchitis(self):
            cough=yes_no("Are you having a persistent cough, which may produce yellow grey mucus (phlegm)?")
            wheezing=yes_no("Are you experiencing Wheezing?")
            chills=yes_no("Are you experiencing chills?")
            chest_tightness=yes_no("Are you having a feeling of tightness in the chest?")
            sore_throat = yes_no("Are you having a sore throat?")
            body_aches=yes_no("Are you having body pains?")
            breathlessness=yes_no("Are you experiencing breathlessness?")
            headache=yes_no("Are you having headache?")
            nose_blocked=yes_no("Are you having a blocked nose or sinuses?")
            count=0
            for string in [headache, cough, wheezing, chills, chest_tightness, sore_throat, body_aches, breathlessness, nose_blocked]:
                if string=="yes":
                    count+=1
    
            if count>=7:
                symptoms = ["Slight Fever", "Cough", "Wheezing", "Chills in body", "Tightness in chest", "Sore throat", "Body aches", "Headache", "Breathlessness", "Blocke nose"]
                suggest_disease("Bronchitis", symptoms)
    
        @Rule(Fact(red_eyes="yes"))
        def askEyeStatus(self):
            self.declare(Fact(eye_burn=yes_no("Do you have a burning sensation in eyes?")))
            self.declare(Fact(eye_crusting=yes_no("Do you get pus or crusting on eyes?")))
            self.declare(Fact(eye_irritation=yes_no("Do you have eye irritation?")))
        
        @Rule(OR(Fact(eye_crusting="yes"), Fact(eye_burn="yes")), salience=1000)
        def disease_Conjunctivitis(self):
            suggest_disease("Conjunctivitis", ["Burning sensation in eyes", "Crusting of eyes", "Redness in eyes"])
    
        @Rule(Fact(eye_irritation="yes"), salience=900)
        def disease_EyeAllergy(self):
            suggest_disease("Eye Allergy", ["Irritation in eyes", "Redness in eyes"])
    
        @Rule(Fact("Normal_Fever"))
        def askRelatedToFever(self):
            self.declare(Fact(chest_pain=yes_no("Are you suffering from chest pain?")))
            self.declare(Fact(abdominal_pain=yes_no("Are you suffering from abdominal pain?")))
            self.declare(Fact(sore_throat=yes_no("Are you suffering from sore throat?")))
            self.declare(Fact(chills=yes_no("Are you having shaking chills?")))
            self.declare(Fact(rashes=yes_no("Are you suffering from rashes on skin?")))
            self.declare(Fact(nausea=yes_no("Did you vomit or feel like vomiting(Nausea)")))
    
        @Rule(AND(Fact("Normal_Fever"), Fact(chest_pain="yes"), Fact(fatigue="yes"), Fact(chills="yes")))
        def askTB(self):
            count=0
            persistent_cough = yes_no("Are you experiencing persistent cough which lasted for more than 2 to 3 weeks?")
            weigh_loss = yes_no("Did you experience unintentional weight loss?")
            night_sweats=yes_no("Are you experiencing Night Sweats?")
            cough_blood=yes_no("Are you coughing up blood?")
            for string in [persistent_cough, weigh_loss, night_sweats, cough_blood]:
                if string=="yes":
                    count+=1
    
            if count>=2:
                suggest_disease("Tuberculosis",["fever", "chest pain", "fatigue", "loss of appetite","persistent cough"])
        
        @Rule(AND(Fact("Normal_Fever"), Fact(fatigue="yes"), Fact(sore_throat="yes")))
        def askInfluenza(self):
            count=0
            weakness=yes_no("Are you experiencing weakness?")
            dry_cough=yes_no("Are you having dry persistent cough?")
            muscle_ache=yes_no("Are you having aching muscles, especially in your back, arms and legs?")
            chills=yes_no("Are you experiencing sweats along with chills?")
            nasal_congestion=yes_no("Are you experiencing nasal congestion?")
            headache=yes_no("Are you experiencing headache?")
            for string in [weakness, dry_cough, muscle_ache, chills, nasal_congestion, headache]:
                if string=="yes":
                    count+=1
    
            if count>=4:
                symptoms = ["Fever", "Fatigue", "Sore throat", "Weakness", "Dry cough", "Muscle aches", "Chills", "Nasal congestion", "Headache"]
                suggest_disease("Influenza", symptoms)
    
        @Rule(AND(Fact("Normal_Fever"), Fact(fatigue="yes"), Fact(abdominal_pain="yes")))
        def askHepatitis(self):
            count=0
            flu_like=yes_no("Are you experiencing flu like symptoms?")
            dark_urine=yes_no("Are you getting dark urine?")
            pale_stool=yes_no("Are you having pale stool?")
            weight_loss=yes_no("Are you experiencing unexplained weight loss?")
            jaundice=yes_no("Are your skin and eyes turning yellow?")
            for string in [flu_like, dark_urine, pale_stool, weight_loss, jaundice]:
                if string=="yes":
                    count+=1
    
            if count>=3:
                symptoms = ["Fever", "Fatigue", "Abdominal pain", "Flu like symptoms", "Dark urine", "Pale stool", "Weight loss", "Yellow eyes and skin(Jaundice)"]
                suggest_disease("Hepatitis", symptoms)
    
        @Rule(AND(Fact("Normal_Fever"), Fact(chest_pain="yes"), Fact(short_breath="yes"), Fact(nausea="yes")))
        def askPneumonia(self):
            count=0
            short_breath=yes_no("Are you experiencing shortness of breath while doing normal activities or even while resting?")
            sweat=yes_no("Are you experiencing sweating along with chills?")
            rapid_breath=yes_no("Are you breathing rapidly?")
            cough=yes_no("Are you having a worsening cough that may produce yellow/green or bloody mucus (phlegm)")
            diarrhea=yes_no("Are you experiencing Diarrhea?")
            for string in [short_breath, sweat, rapid_breath, cough, diarrhea]:
                if string=="yes":
                    count+=1
    
            if count>=3:
                symptoms = ["Fever", "Chest pain", "Shortness in breath", "Nausea", "Sweating with chills", "Rapid breathing", "Cough with phlegm", "Diarrhea"]
                suggest_disease("Pneumonia", symptoms)
    
        @Rule(AND(Fact("Normal_Fever"), Fact(chills="yes"), Fact(abdominal_pain="yes"), Fact(nausea="yes")))
        def askMalaria(self):
            count=0
            headache=yes_no("Are you experiencing headache?")
            sweat=yes_no("Are you experiencing sweating frequently?")
            cough=yes_no("Are you coughing frequently")
            weakness=yes_no("Are you experiencing weakness?")
            muscle_pain=yes_no("Are you having intense muscle pain?")
            back_pain=yes_no("Are you having lower back pain?")
            for string in [headache, sweat, weakness, cough, muscle_pain, back_pain]:
                if string=="yes":
                    count+=1
    
            if count>=4:
                symptoms = ["Fever", "Chills", "Abdominal pain", "Nausea", "Headache", "Sweating", "Cough", "Weakness", "Muscle pain", "Back pain"]
                suggest_disease("Malaria", symptoms)
    
        @Rule(AND(Fact("Normal_Fever"), Fact(rashes="yes")))
        def askHIV(self):
            count=0
            headache=yes_no("Are you experiencing headache?")
            muscle_ache=yes_no("Are you having muscle aches and joint pain?")
            sore_throat=yes_no("Are you experiencing sore throat and painful mouth sores?")
            lymph=yes_no("Are you experiencing swollen lymph glands especially on the neck?")
            diarrhea=yes_no("Are you experiencing Diarrhea?")
            cough=yes_no("Are you coughing frequently")
            weigh_loss = yes_no("Did you experience unintentional weight loss?")
            night_sweats=yes_no("Are you experiencing Night Sweats?")
            for string in [headache, muscle_ache, sore_throat, lymph, diarrhea, cough, weigh_loss, night_sweats]:
                if string=="yes":
                    count+=1
    
            if count>=6:
                symptoms = ["Fever", "Rashes", "Headache", "Muscle ache", "Sore throat", "Swollen lymph nodes", "Diarrhea", "Cough", "Weight loss", "Night sweat"]
                suggest_disease("AIDS", symptoms)
    
        @Rule(AND(Fact("Normal_Fever"), Fact(nausea="yes")))
        def askPancreatitis(self):
            count=0
            upper_abdominal_pain=yes_no("Are you experiencing upper abdominal pain? ")
            abdominal_eat=yes_no("Is the abdominal pain becoming verse after eating?")
            hearbeat=yes_no("Is your heartbeat at high rate?")
            weigh_loss = yes_no("Did you experience unintentional weight loss?")
            oily_stool=yes_no("Are you having oily smelly stools?")
            for string in [upper_abdominal_pain, abdominal_eat, hearbeat, weigh_loss, oily_stool]:
                if string=="yes":
                    count+=1
    
            if count>=3:
                symptoms = ["Nausea", "Fever", "Upper abdominal pain", "Heartbeat", "Weight loss", "Oily and smelly stool"]
                suggest_disease("Pancreatitis", symptoms)
    
        @Rule(AND(Fact("Normal_Fever"), Fact(fatigue="yes"), Fact(short_breath="yes"), Fact(nausea="yes")))
        def askCorona(self):
            chills=yes_no("Are you having chills sometimes with shaking?")
            cough=yes_no("Do you cough frequently?")
            body_aches=yes_no("Are you having body aches?")
            headache=yes_no("Are you experiencing headache?")
            sore_throat=yes_no("Are you experiencing sore throat and painful mouth sores?")
            lose_smell=yes_no("Did you lose your sense of smell and taste considerably?")
            diarrhea=yes_no("Are you experiencing Diarrhea?")
            count=0
            for string in [chills, body_aches, headache, sore_throat, lose_smell, diarrhea]:
                if string=="yes":
                    count+=1
    
            if count>=4:
                symptoms = ["Fever", "Fatigue", "Shortness in breath", "Nausea", "Chills", "Cough", "Body aches", "Headache", "Sorethroat", "Diarrhea", "Loose sense of taste/smell"]
                suggest_disease("Corona Virus", symptoms)
    
        # Medical History based rules for enhanced diagnosis
    
        @Rule(AND(Fact(diabetes="yes"), Fact(fatigue="yes"), Fact(extreme_thirst="yes"), Fact(extreme_hunger="yes")), salience=100)
        def diabetesWithHistory(self):
            frequent_urination=yes_no("Is your Urination more frequent than before?")
            weight_loss=yes_no("Did you lose your weight unintentionally?")
            irratabiliry=yes_no("Are you more irritable now a days?")
            blurred_vision=yes_no("Did your vision get blurred?")
            frequent_infections=yes_no("Are you having frequent infections such as gums or skin infections")
            sores=yes_no("Are your sores healing slowly?")
            count=0
            for string in [frequent_urination, weight_loss, irratabiliry, blurred_vision, frequent_infections, sores]:
                if string=="yes":
                    count+=1
    
            if count>=3:  # Lower threshold for diabetic patients
                symptoms = ["Fatigue", "Extreme thirst", "Extreme hunger", "Weight loss", "Blurred vision", "Frequent infections", "Frequent urination", "Irritability", "Slow healing of sores"]
                print("\n[Note: You have diabetes - this condition may be related to your diabetes management]")
                suggest_disease("Diabetes", symptoms)
    
        @Rule(AND(Fact(hypertension="yes"), Fact(short_breath="yes"), Fact(chest_pain="yes")), salience=100)
        def heartIssueWithHypertension(self):
            heaviness=yes_no("Did you have feeling of heaviness or tightness, usually in the centre of the chest, which may spread to the arms, neck, jaw, back or stomach?")
            sweating=yes_no("Are you sweating frequently?")
            dizziness=yes_no("Are you feeling dizzy?")
            burning=yes_no("Do you feel burning sensation near heart?")
            count=0
            for string in [heaviness, sweating, dizziness, burning]:
                if string=="yes":
                    count+=1
    
            if count>=2:
                symptoms = ["Shortness in breath", "Chest pain", "Heaviness", "Sweating", "Dizziness", "Burning sensation near heart"]
                print("\n[Note: You have hypertension - heart conditions require careful monitoring with high blood pressure]")
                suggest_disease("Coronary Arteriosclerosis", symptoms)
    
        @Rule(AND(Fact(heart_disease="yes"), Fact(fatigue="yes"), Fact(short_breath="yes")), salience=100)
        def cardiacSymptomsWithHistory(self):
            irregular_heartbeat=yes_no("Are you experiencing irregular heartbeat?")
            weakness=yes_no("Are you feeling weak?")
            pale_skin=yes_no("Has your skin turned pale or yellowish?")
            lightheadedness=yes_no("Are you having dizziness or light headedness?")
            cold_hands_feet=yes_no("Are you having cold hands and feet?")
            count=0
            for string in [irregular_heartbeat, weakness, pale_skin, lightheadedness, cold_hands_feet]:
                if string=="yes":
                    count+=1
    
            if count>=3:
                symptoms = ["Shortness in breath", "Fatigue", "Irregular heartbeat", "Weakness", "Pale skin", "Dizziness", "Cold limbs"]
                print("\n[Note: You have a heart condition - please consult your cardiologist]")
                suggest_disease("Anemia", symptoms)
    
        @Rule(AND(Fact(thyroid_disorder="yes"), Fact(fatigue="yes")), salience=100)
        def thyroidSymptomsWithHistory(self):
            depression=yes_no("Are you feeling depressed now a days?")
            constipation=yes_no("Are you experiencing constipation?")
            feeling_cold=yes_no("Are you feeling cold?")
            dry_skin=yes_no("Has your skin became drier?")
            dry_hair=yes_no("Is your hair too becoming dry and also thinner?")
            weight_gain=yes_no("Did you gain your weight considerably?")
            decreased_sweating=yes_no("Are you not sweating much as earlier?")
            slowed_heartrate=yes_no("Did your heart rate slow down?")
            pain_joints=yes_no("Are you experiencing pain and stiffness in joints?")
            hoarseness=yes_no("Is your voice changing abnormally?")
            count=0
            for string in [depression, constipation, feeling_cold, dry_skin, dry_hair, weight_gain, decreased_sweating, slowed_heartrate, pain_joints, hoarseness]:
                if string=="yes":
                    count+=1
    
            if count>=5:  # Lower threshold for thyroid patients
                symptoms = ["Fatigue", "Depression", "Constipation", "Cold feeling", "Dry skin", "Dry hair", "Weight gain", "Decreased sweating", "Slow heart rate", "Joint pains", "Hoarseness in voice"]
                print("\n[Note: You have a thyroid disorder - this may be related to your condition]")
                suggest_disease("Hypothyroidism", symptoms)
    
        @Rule(AND(Fact(kidney_disease="yes"), Fact(fatigue="yes"), Fact(appetite_loss="yes")), salience=100)
        def kidneyRelatedSymptoms(self):
            print("\n[Note: You have kidney disease - some medications may not be suitable]")
            # Continue with existing logic but with awareness
    
        @Rule(AND(Fact(liver_disease="yes"), Fact(fatigue="yes"), Fact(nausea="yes")), salience=100)
        def liverRelatedSymptoms(self):
            print("\n[Note: You have liver disease - please consult your doctor before taking any new medications]")
    
    

else:
    class MedicalExpert:
        def __init__(self, *args, **kwargs):
            raise ImportError("experta is required to run the console expert system.")

if __name__ == "__main__":
    engine = MedicalExpert()
    engine.reset()
    engine.run()
    print("The symptoms did not match with any of diseases in my database.")
