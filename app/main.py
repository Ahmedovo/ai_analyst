"""Entry point for the AI data analyst application."""

from app.agents.analyst import AnalystAgent


def main() -> None:
    agent = AnalystAgent()
    result = agent.analyze("data/sales.csv", question="Give me an overview of this dataset.")
    print(result)


if __name__ == "__main__":
    main()
