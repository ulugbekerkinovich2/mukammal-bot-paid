module.exports = {
    apps: [
      {
        name: "@mentalaba/dtm-paper-test-registration",
        cwd: "/data/schools/mentalaba-dtm-paper-test-registration",
        script: "/data/schools/mentalaba-dtm-paper-test-registration/venv/bin/python",
        args: "app.py",
        interpreter: "none",
        env: {
          PYTHONUNBUFFERED: "1",
        },
        autorestart: true,
        restart_delay: 5000,
        max_restarts: 20,
        time: true,
      },
    ],
  };