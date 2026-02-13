pyenv versions
pyenv local 3.8.10
python --version
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

setup .env configs

nano pm2.config.js


pm2 start pm2.config.js
pm2 logs iapplybot
