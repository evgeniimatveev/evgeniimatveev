import datetime
import random

# Path to the README file
README_FILE = "README.md"

# List of random MLOps-related phrases
PHRASES = [
    "🚀 MLOps is Automation!",
    "📊 SQL for ML Experiments",
    "⚡ Track your models like a pro!",
    "🛠️ MLOps + CI/CD = 💙",
    "📡 Deploy ML models with FastAPI 🌐",
    "📈 Monitor metrics with W&B | MLflow 🛠️",
    "🐍 Python | R | PostgreSQL for Data Science 📊",
    "🦾 Automate ML Pipelines with GitHub Actions ⚡",
    "🔄 Data Versioning with DVC | LakeFS 🌊",
    "📦 Containerize ML Models with Docker 🐳",
    "🔬 Hyperparameter Tuning with W&B Sweeps 🎯",
    "🤖 Deploy AI Chatbots using LLMs 🛠️",
    "💾 Feature Engineering for ML Success 🚀",
    "🛡️ Secure ML Pipelines with MLOps Best Practices 🔒",
    "📜 Automate SQL Queries for MLflow Tracking ⏳",
    "💡 Optimize ML Experiments with Bayesian Tuning 🎯",
    "🖥️ Build Interactive Dashboards in Tableau | Power BI 📊",
    "🎭 Track and Compare Models with Experiment Versioning 📈",
]

def generate_new_readme():
    """
    Reads the README file, updates the last updated timestamp, 
    and adds a randomly selected MLOps phrase.
    """
    with open(README_FILE, "r", encoding="utf-8") as file:
        content = file.readlines()

    updated_content = []
    timestamp_updated = False
    phrase_updated = False
    new_phrase = random.choice(PHRASES)  # Select a random phrase

    for line in content:
        if line.startswith("Last updated:"):
            # Update the timestamp
            updated_content.append(f"Last updated: {datetime.datetime.utcnow()} UTC\n")
            timestamp_updated = True
        elif line.startswith("🔥 MLOps Insight:"):
            # Update the random phrase
            updated_content.append(f"🔥 MLOps Insight: {new_phrase}\n")
            phrase_updated = True
        else:
            updated_content.append(line)

    # If no timestamp found, append it at the end
    if not timestamp_updated:
        updated_content.append(f"\nLast updated: {datetime.datetime.utcnow()} UTC\n")

    # If no phrase found, append it at the end
    if not phrase_updated:
        updated_content.append(f"\n🔥 MLOps Insight: {new_phrase}\n")

    with open(README_FILE, "w", encoding="utf-8") as file:
        file.writelines(updated_content)

if __name__ == "__main__":
    generate_new_readme()
    print("✅ README successfully updated!")
