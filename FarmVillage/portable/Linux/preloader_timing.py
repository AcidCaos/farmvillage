"""Use the original preloader's five-second Farm of the Day photo timer.

The recovered Preloader constructor multiplies flashvar fotdChangeTime by 1000.
Without that variable the int field becomes zero, producing a busy photo timer.
The Ruffle page also receives a bounded 60-second synchronous script budget for
the full catalogue index; frame rate and game/progress timers do not change.
"""

import re


SECONDS_PER_PHOTO = 5
SCRIPT_EXECUTION_SECONDS = 60
_PHOTOS = re.compile(r"(?P<separator>&(?:amp;)?)fotd=")
_INTERVAL = re.compile(r"(?P<separator>&(?:amp;)?)fotdChangeTime=[^&\s\\\"'<>]*")
_CONFIG = re.compile(r"(window\.RufflePlayer\.config\s*=\s*\{)(.*?)(\}\s*;)", re.S)
_BUDGET = re.compile(r'''(?P<key>(?:"maxExecutionDuration"|'maxExecutionDuration'|\bmaxExecutionDuration)\s*:\s*)(?P<value>[^\s,}]+)''')
_LOADER = re.compile(r'''<script\b[^>]*\bsrc\s*=\s*["'][^"']*ruffle\.js["'][^>]*>''', re.I)


def execution_budget(document):
    """Set the existing early Ruffle config's finite synchronous script budget.

    The full recovered catalogue indexes 111,206 definitions. A real browser
    trace exceeded Ruffle's default 15 seconds and abandoned its completion
    callback. Sixty seconds leaves a limit while allowing slower hosts to finish.
    """
    configs = list(_CONFIG.finditer(document))
    loader = _LOADER.search(document)
    if len(configs) != 1 or loader is None or configs[0].end() > loader.start():
        raise ValueError("The Ruffle page must configure its player before loading ruffle.js.")
    config = configs[0]
    body = config[2]
    budgets = list(_BUDGET.finditer(body))
    if len(budgets) > 1:
        raise ValueError("The Ruffle config has duplicate script execution budgets.")
    if budgets:
        body = _BUDGET.sub(lambda match: match["key"] + str(SCRIPT_EXECUTION_SECONDS), body)
    else:
        body = f" maxExecutionDuration: {SCRIPT_EXECUTION_SECONDS}," + body
    return document[:config.start()] + config[1] + body + config[3] + document[config.end():]


def photo_interval(document):
    """Return the same HTML with exactly one five-second slideshow parameter.

    Keep all photo URLs, unrelated flashvars, markup and escaping intact. Both
    the literal ampersands in the Ruffle JS and HTML-encoded variants work.
    """
    photos = list(_PHOTOS.finditer(document))
    intervals = list(_INTERVAL.finditer(document))
    if len(photos) != 1 or len(intervals) > 1:
        raise ValueError("The game page must contain one recognized preloader photo list.")
    if intervals:
        return _INTERVAL.sub(lambda match: match["separator"] + "fotdChangeTime=5", document)
    photo = photos[0]
    parameter = photo["separator"] + "fotdChangeTime=5"
    return document[:photo.start()] + parameter + document[photo.start():]


def configure_preloader(app):
    """Apply the bounded flashvar edit to rendered game pages on this host."""
    if app.extensions.get("farmvillage_preloader_timing"):
        return
    app.extensions["farmvillage_preloader_timing"] = {"secondsPerPhoto": SECONDS_PER_PHOTO, "scriptExecutionSeconds": SCRIPT_EXECUTION_SECONDS}
    from flask import request

    @app.after_request
    def farmvillage_preloader_timing(response):
        if (request.path not in ("/ruffle.html", "/play.html")
                or response.status_code != 200 or response.mimetype != "text/html"):
            return response
        original = response.get_data(as_text=True)
        try:
            configured = photo_interval(original)
            if request.path == "/ruffle.html":
                configured = execution_budget(configured)
        except ValueError:
            # A login/error page or a changed upstream template must remain
            # usable. Surface the missing timing contract in the server log.
            app.logger.warning("FarmVillage loading config: game page has no recognized photo list or early Ruffle config.")
            return response
        response.set_data(configured)
        return response
