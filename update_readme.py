import datetime

# Path to the README file
README_FILE = "README.md"

# Generate updated content
def generate_new_readme():
    with open(README_FILE, "r", encoding="utf-8") as file:
        content = file.readlines()
    
    # Add or update timestamp in README
    updated_content = []
    for line in content:
        if line.startswith("Last updated:"):
            updated_content.append(f"Last updated: {datetime.datetime.utcnow()} UTC\n")
        else:
            updated_content.append(line)
    
    # If no timestamp found, add it
    if not any(line.startswith("Last updated:") for line in updated_content):
        updated_content.append(f"\nLast updated: {datetime.datetime.utcnow()} UTC\n")
    
    with open(README_FILE, "w", encoding="utf-8") as file:
        file.writelines(updated_content)

# Run the update
if __name__ == "__main__":
    generate_new_readme()
    print("✅ README successfully updated!")
