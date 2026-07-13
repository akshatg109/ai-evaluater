"""Run the AI Answer Sheet Evaluator with: python3 app.py."""

import os

from evaluator_app.application import create_app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.getenv("FLASK_ENV") == "development")
