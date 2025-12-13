import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "RetroFitter Plus is LIVE 🚀", 200

@app.route("/health")
def health():
    return "OK", 200
