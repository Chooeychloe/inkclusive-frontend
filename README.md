# FairWrite (Server-Side)

FairWrite is a web-based text editor that provides grammar and gender-fair revisions. Built with FastAPI, it integrates with powerful NLP tools like `spaCy` and `language-tool-python` to enhance writing for clarity, accuracy, and inclusivity.

## ✨ Features

- **Grammar Check:** Detects and suggests corrections for grammatical errors.
- **Gender-Fair Language:** Encourages gender-neutral language and avoids biased terms.
- **Custom Preferred Pronoun:** Users can specify their preferred pronouns for personalized suggestions.
- **Admin Gender Terms Control:** Admins can manage and customize gender term revisions (CRUD support).

## 🛠️ Tech Stack

- **FastAPI:** A modern, high-performance web framework for building APIs with Python 3.8+ based on standard Python type hints. It enables rapid development and automatic interactive API documentation.
- **Uvicorn:** A lightning-fast ASGI server implementation, used to serve FastAPI applications in production and development environments.
- **LanguageTool:** An open-source grammar, style, and spell checker. Integrated via `language-tool-python`, it analyzes text for grammatical errors and suggests improvements.
- **spaCy:** An advanced Natural Language Processing (NLP) library for Python. Used for tokenization, part-of-speech tagging, and other linguistic features to support gender-fair and inclusive language suggestions.

## 📦 Installation

Follow these steps to set up the project:

### 1. Install Python and Java

Make sure you have **Python 3.8 or higher** installed, as this project relies on recent Python features. You can download the latest version from the [official Python website](https://www.python.org/downloads/).  
To verify your Python installation, run:

```bash
python --version
```

Additionally, **Java JDK 21 or newer** is required for running LanguageTool, which handles grammar checking. Download the JDK from the [Oracle Java Downloads page](https://www.oracle.com/javatechnologies/downloads/), or use your system's package manager.  
To confirm Java is installed, run:

```bash
java -version
```

### 2. Clone the Repository

```bash
git clone https://github.com/Fair-Write/Server-Side.git
cd fairwrite
```

### 3. Create and Activate a Virtual Environment

```bash
python -m venv .venv
```

- **On macOS/Linux:**
     ```bash
     source .venv/bin/activate
     ```
- **On Windows:**
     ```bash
     .venv\Scripts\activate
     ```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Download spaCy Model

```bash
python -m spacy download en_core_web_sm
```

### 6. Run the Application

```bash
uvicorn main:app --port 80
```

The app will be available at [http://127.0.0.1:80/](http://127.0.0.1:80/).

---

## 🚀 Frontend Integration

For the official frontend interface, refer to the [FairWrite Client-Side](https://github.com/yourusername/fairwrite-client) repository.
