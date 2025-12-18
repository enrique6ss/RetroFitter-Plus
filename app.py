from flask import Flask, render_template, request, redirect

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def intake():
    if request.method == "POST":
        # For now we just accept the form
        # Next step we save this to the database
        return redirect("/success")

    return render_template("intake.html")

@app.route("/success")
def success():
    return render_template("success.html")

@app.route("/health")
def health():
    return "OK", 200
