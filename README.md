name: Update GitHub Profile Stats

on:
  schedule:
    - cron: "0 */12 * * *"  # Обновление каждые 12 часов
  workflow_dispatch:  # Возможность запустить вручную

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Update GitHub Stats
        run: curl -s -o /dev/null "https://github-readme-stats.vercel.app/api?username=evgeniimatveev&show_icons=true&theme=gradient"

      - name: Update GitHub Streak
        run: curl -s -o /dev/null "https://github-readme-streak-stats.herokuapp.com/?user=evgeniimatveev&theme=gruvbox"

      - name: Update Top Languages
        run: curl -s -o /dev/null "https://github-readme-stats.vercel.app/api/top-langs/?username=evgeniimatveev&layout=compact&theme=dracula"

      - name: Update WakaTime Stats
        run: curl -s -o /dev/null "https://github-readme-stats.vercel.app/api/wakatime?username=evgeniimatveev&theme=gruvbox"

      - name: Update GitHub Activity Graph
        run: curl -s -o /dev/null "https://github-readme-activity-graph.vercel.app/graph?username=evgeniimatveev&theme=react-dark"

      - name: Update GitHub Trophies
        run: curl -s -o /dev/null "https://github-profile-trophy.vercel.app/?username=evgeniimatveev&theme=onedark"
