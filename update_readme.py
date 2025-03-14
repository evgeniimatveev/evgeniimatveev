import datetime
import random

# Path to the README file
README_FILE = "README.md"

# Context-based phrases
MORNING_QUOTES = [
    "Time for some coffee and MLOps ☕",
    "Start your morning with automation! 🛠️",
    "Good morning! Let's optimize ML experiments! 🎯"
]

AFTERNOON_QUOTES = [
    "Keep pushing your MLOps pipeline forward! 🔧",
    "Optimize, deploy, repeat! 🔄",
    "Perfect time for CI/CD magic! ⚡"
]

EVENING_QUOTES = [
    "Evening is the best time to track ML experiments 🌙",
    "Relax and let automation handle your work 🤖",
    "Wrap up the day with some Bayesian tuning 🎯"
]

DAY_OF_WEEK_QUOTES = {
    "Monday": "Start your week strong! 🚀",
    "Tuesday": "Keep up the momentum! 🔥",
    "Wednesday": "Halfway to the weekend, keep automating! 🛠️",
    "Thursday": "Test, iterate, deploy! 🚀",
    "Friday": "Wrap it up like a pro! 🔥",
    "Saturday": "Weekend automation vibes! 🎉",
    "Sunday": "Prepare for an MLOps-filled week! ⏳"
}

EXTRA_EMOJIS = ["🚀", "⚡", "🔥", "💡", "🎯", "🔄", "📈", "🛠️"]

# Function to generate dynamic quote
def get_dynamic_quote():
    now = datetime.datetime.utcnow()
    day_of_week = now.strftime("%A")
    hour = now.hour

    if 6 <= hour < 12:
        selected_quote = random.choice(MORNING_QUOTES)
    elif 12 <= hour < 18:
        selected_quote = random.choice(AFTERNOON_QUOTES)
    else:
        selected_quote = random.choice(EVENING_QUOTES)

    # Add a weekday-specific boost
    selected_quote += f" | {DAY_OF_WEEK_QUOTES[day_of_week]}"

    # Add a random emoji at the end for fun
    selected_quote += f" {random.choice(EXTRA_EMOJIS)}"

    return selected_quote

# Generate updated content
def generate_new_readme():
    with open(README_FILE, "r", encoding="utf-8") as file:
        content = file.readlines()

    now = datetime.datetime.utcnow()
    dynamic_quote = get_dynamic_quote()

    # Add or update timestamp and quote in README
    updated_content = []
    for line in content:
        if line.startswith("Last updated:"):
            updated_content.append(f"Last updated: {now} UTC\n")
        elif line.startswith("🔥 MLOps Insight:"):
            updated_content.append(f"🔥 MLOps Insight: 💡 {dynamic_quote}\n")
        else:
            updated_content.append(line)

    # If no timestamp found, add it
    if not any(line.startswith("Last updated:") for line in updated_content):
        updated_content.append(f"\nLast updated: {now} UTC\n")

    # If no MLOps insight found, add it
    if not any(line.startswith("🔥 MLOps Insight:") for line in updated_content):
        updated_content.append(f"\n🔥 MLOps Insight: 💡 {dynamic_quote}\n")

    with open(README_FILE, "w", encoding="utf-8") as file:
        file.writelines(updated_content)

    print(f"✅ README successfully updated! ({now} UTC)")
    print(f"📝 Selected Quote: {dynamic_quote}")

# Run the update
if __name__ == "__main__":
    generate_new_readme()
