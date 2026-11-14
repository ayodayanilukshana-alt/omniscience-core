import json
import urllib.request


class OmniscientBrain:
    def __init__(self, repo_owner="ayodayanilukshana-alt", repo_name="omniscience-core"):
        self.raw_base = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/main/brain"
        self.state = self._fetch_json("omniscient_state.json")

    def _fetch_json(self, filename):
        try:
            req = urllib.request.Request(f"{self.raw_base}/{filename}", headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return {}

    def get_viral_laws(self):
        return self.state.get("algorithmic_laws_vault", {})
