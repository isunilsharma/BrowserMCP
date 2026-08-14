"""Tiny Flask fixture site used by integration tests.

Why Flask: integration tests need a real HTTP server with cookies, redirects,
form POST handling, and a JS modal. A static-HTML fileserver wouldn't exercise
the write-gate / cookie / redirect paths we want to cover. Flask is in the
dev-dependencies so this only matters in the integration test environment.

The app is wired up by tests/integration/conftest.py to bind to localhost:0
(random free port) so multiple test workers don't collide.
"""
from __future__ import annotations

from flask import (
    Flask,
    make_response,
    redirect,
    request,
)


def create_app() -> Flask:
    """Build the test fixture Flask app.

    Kept as a factory so the conftest fixture can spawn a fresh instance per
    test session and pass it through a werkzeug dev server.
    """
    app = Flask(__name__)
    # Predictable session cookie name so the /login + /protected tests can
    # assert on it directly without depending on framework defaults.
    app.config["SESSION_COOKIE_NAME"] = "browsermcp_test_session"

    @app.get("/form")
    def form_page() -> str:
        # Inputs use both `name` and explicit `<label for=...>` so the
        # _PlaywrightHandler.get_by_label path and the input[name] selector
        # path in _BrowserUseHandler both resolve cleanly.
        return """
        <!doctype html>
        <html><head><title>Contact</title></head>
        <body>
          <h1>Contact form</h1>
          <form action="/submit" method="post">
            <label for="email">Email</label>
            <input id="email" name="email" type="email" aria-label="Email" />
            <br/>
            <label for="message">Message</label>
            <textarea id="message" name="message" aria-label="Message"></textarea>
            <br/>
            <button type="submit" aria-label="Submit">Submit</button>
          </form>
        </body></html>
        """

    @app.post("/submit")
    def submit() -> str:
        email = request.form.get("email", "")
        message = request.form.get("message", "")
        # Echo the values back so tests can assert that the POST actually
        # delivered the right payload (not just that the page rendered).
        return f"""
        <!doctype html>
        <html><head><title>Submitted</title></head>
        <body>
          <h1>Thanks for your message</h1>
          <p>We received your message from <span id="email">{email}</span>.</p>
          <p id="message">{message}</p>
        </body></html>
        """

    @app.get("/table")
    def table_page() -> str:
        # Three deterministic rows + a pager link so test_form_fill or a
        # future extract-shaped test can exercise the {name, value, delta}
        # schema against a known-good DOM.
        return """
        <!doctype html>
        <html><head><title>Metrics</title></head>
        <body>
          <h1>Metrics</h1>
          <table id="metrics">
            <thead>
              <tr><th>name</th><th>value</th><th>delta</th></tr>
            </thead>
            <tbody>
              <tr><td>alpha</td><td>10</td><td>+1</td></tr>
              <tr><td>beta</td><td>20</td><td>-2</td></tr>
              <tr><td>gamma</td><td>30</td><td>+3</td></tr>
            </tbody>
          </table>
          <a href="/table?page=2" id="next">Next</a>
        </body></html>
        """

    @app.get("/modal")
    def modal_page() -> str:
        # Modal is hidden until click — covers the wait_for(text=...) path
        # because the text only appears in the DOM after a JS event runs.
        return """
        <!doctype html>
        <html><head><title>Modal</title></head>
        <body>
          <h1>Modal demo</h1>
          <button id="open" aria-label="Open dialog"
                  onclick="document.getElementById('m').style.display='block'">
            Open dialog
          </button>
          <div id="m" role="dialog" aria-label="Confirmation"
               style="display:none">
            <p>Modal opened successfully</p>
            <button aria-label="Close"
                    onclick="document.getElementById('m').style.display='none'">
              Close
            </button>
          </div>
        </body></html>
        """

    @app.get("/login")
    def login_page() -> str:
        # GET shows the form; POST is handled by login_submit below. Kept
        # split so /login can also be the redirect target for /protected.
        return """
        <!doctype html>
        <html><head><title>Login</title></head>
        <body>
          <h1>Login</h1>
          <form action="/login" method="post">
            <label for="username">Username</label>
            <input id="username" name="username" aria-label="Username" />
            <button type="submit" aria-label="Sign in">Sign in</button>
          </form>
        </body></html>
        """

    @app.post("/login")
    def login_submit():
        # Any non-empty username "succeeds" — we only care about the cookie
        # path for the protected-route test, not real auth.
        username = request.form.get("username", "").strip()
        resp = make_response(redirect("/protected"))
        if username:
            # `browsermcp_test_session` is what /protected checks for below.
            resp.set_cookie("browsermcp_test_session", username)
        return resp

    @app.get("/protected")
    def protected():
        # Mirrors a real SSO-gated page: no cookie → redirect to /login.
        # The integration tests don't actually need to land here — they
        # only need to observe the redirect when the cookie is missing.
        if not request.cookies.get("browsermcp_test_session"):
            return redirect("/login")
        return """
        <!doctype html>
        <html><head><title>Protected</title></head>
        <body><h1>Protected content</h1></body></html>
        """

    return app


if __name__ == "__main__":
    # Allow `python tests/fixtures/site/app.py` for quick manual sanity checks
    # outside the pytest harness. Not used by the test fixture itself.
    create_app().run(host="127.0.0.1", port=5050, debug=False)
