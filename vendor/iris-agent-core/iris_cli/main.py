"""Forward ``-m iris_cli.main`` to iris_agent_cli.main."""
from iris_agent_cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
