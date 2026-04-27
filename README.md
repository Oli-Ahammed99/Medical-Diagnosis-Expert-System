# Medical Expert System

An expert system that helps diagnose possible diseases by asking symptom and medical-history questions. The project includes both a console version and a local web version with treatment information and PDF download support.

## About The Project

The system asks the user a sequence of questions and uses rule-based logic to match the answers with a likely disease. When a disease is detected, the web version can show related treatment information from the `Treatment` folder and download it as a PDF.

This project is for educational purposes only and is not a substitute for professional medical advice.

## Dependencies

- Python
- Flask
- Experta

The `.venv` folder is not included in this repository because virtual environments are local machine files. Create your own virtual environment if needed, then install the required packages from `requirements.txt`.

```sh
pip install -r requirements.txt
```

## How To Run

### Web Version

Open `web.py` in VS Code, right-click inside the file, and select:

```text
Run Python File
```

or:

```text
Run Python File in Dedicated Terminal
```

The site should open automatically. If it does not, open this URL in your browser:

```text
http://localhost:5000
```

### Console Version

Run:

```sh
python expert.py
```

## Project Layout

```text
Root directory
|-- ExpertSystemDesign/       Design images for the expert system
|-- Treatment/
|   |-- html/                 Treatment pages generated from markdown
|   |-- markdown/             Treatment information source files
|-- diseases_list.txt
|-- expert.py                 Console expert system and diagnosis engine
|-- web.py                    Local Flask web application
|-- symptoms.ods              Disease and symptom spreadsheet
|-- requirements.txt          Python package dependencies
|-- LICENSE
|-- README.md
```

## Project Contributors

- Oli Ahammed
- Sabbir Hossen
- Mehedi Hasan
- Shafiq Rahman Nirzon

## License

Distributed under the NSU License. See `LICENSE` for more information.

Project Link: https://github.com/Oli-Ahammed99/Medical-Diagnosis-Expert-System
