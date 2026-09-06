"""Ansible 실행 전에 HTTPS/Slack 템플릿의 구조를 검증한다."""
import unittest
from pathlib import Path

try:
    # RHEL 계열 ansible-core는 Jinja2를 _vendor에 포함할 수 있다.
    try:
        import ansible  # noqa: F401
    except ImportError:
        pass
    import jinja2
    import yaml
except ImportError:
    jinja2 = yaml = None

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipIf(jinja2 is None or yaml is None, "Ansible Python의 Jinja2/PyYAML 필요")
class WebTemplateTests(unittest.TestCase):
    def setUp(self):
        self.env = jinja2.Environment(undefined=jinja2.StrictUndefined, trim_blocks=True)
        import json
        self.env.filters["to_json"] = json.dumps
        self.variables = {
            "web_listen_address": "172.16.8.10",
            "web_portal_hostname": "cloud.lab.test",
            "web_grafana_hostname": "grafana.lab.test",
            "web_grafana_url": "https://grafana.lab.test",
            "web_certificate_directory": "/etc/pki/nginx/private-cloud",
        }

    def render(self, name):
        return self.env.from_string((ROOT / name).read_text(encoding="utf-8")).render(**self.variables)

    def test_nginx_only_exposes_named_tls_frontends(self):
        result = self.render("automation/ansible/templates/private-cloud-web.conf.j2")
        self.assertEqual(3, result.count("listen 172.16.8.10:443 ssl"))
        self.assertIn("ssl_reject_handshake on;", result)
        self.assertIn("proxy_pass http://127.0.0.1:3000;", result)
        self.assertIn("proxy_pass http://127.0.0.1:8000;", result)
        self.assertNotIn("172.16.2.10", result)

    def test_slack_urls_and_newlines_survive_jinja_and_yaml(self):
        self.variables["monitoring_slack_webhook_url"] = {
            "stdout": "https://hooks.slack.com/services/EXAMPLE/EXAMPLE/EXAMPLE"
        }
        config = yaml.safe_load(self.render("monitoring/alertmanager/alertmanager.yml.j2"))
        slack = config["receivers"][1]["slack_configs"][0]
        self.assertIn("https://grafana.lab.test/d/private-cloud-instances", slack["title_link"])
        self.assertIn("https://grafana.lab.test/d/private-cloud-nodes", slack["text"])
        self.assertIn("\n*대상*", slack["text"])
        self.assertNotIn("\\n", slack["text"])
        self.assertNotIn("172.16.2.10", slack["text"])

    def test_empty_slack_secret_still_renders(self):
        self.variables["monitoring_slack_webhook_url"] = {"stdout": ""}
        config = yaml.safe_load(self.render("monitoring/alertmanager/alertmanager.yml.j2"))
        self.assertEqual("discard", config["route"]["receiver"])
        self.assertEqual([{"name": "discard"}], config["receivers"])

    def test_fast_alert_delivery_keeps_repeat_notifications_throttled(self):
        self.variables["monitoring_slack_webhook_url"] = {"stdout": ""}
        route = yaml.safe_load(self.render("monitoring/alertmanager/alertmanager.yml.j2"))["route"]
        self.assertEqual("5s", route["group_wait"])
        self.assertEqual("15s", route["group_interval"])
        self.assertEqual("4h", route["repeat_interval"])

    def test_scrape_timing_and_rule_hold_periods(self):
        self.variables.update({
            "groups": {"monitoring_nodes": []},
            "monitoring_instance_discovery_token": {"stdout": "test-token"},
        })
        config = yaml.safe_load(self.render("monitoring/prometheus/prometheus.yml.j2"))
        self.assertEqual("10s", config["global"]["scrape_interval"])
        self.assertEqual("5s", config["global"]["scrape_timeout"])
        self.assertEqual("10s", config["global"]["evaluation_interval"])
        rules = yaml.safe_load((ROOT / "monitoring/prometheus/rules/private-cloud-alerts.yml").read_text(encoding="utf-8"))
        holds = {rule["alert"]: rule["for"] for group in rules["groups"] for rule in group["rules"]}
        for name in ("ComputeNodeDown", "StorageNodeDown", "ManagedInstanceExporterDown"):
            self.assertEqual("30s", holds[name])
        self.assertEqual("10m", holds["GlusterBrickCapacityHigh"])


if __name__ == "__main__":
    unittest.main()
