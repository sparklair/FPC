from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    parameter: str
    subsystem: str
    label: str
    warning: float
    critical: float
    hysteresis: float
    direction: str
    unit: str

    def severity(self, value, previous="NORMAL"):
        sign = 1 if self.direction == "high" else -1
        value, warning, critical = value * sign, self.warning * sign, self.critical * sign
        if value >= critical or (previous == "CRITICAL" and value > critical - self.hysteresis):
            return "CRITICAL"
        if value >= warning or (previous != "NORMAL" and value > warning - self.hysteresis):
            return "WARNING"
        return "NORMAL"

    def threshold(self, severity):
        return self.critical if severity == "CRITICAL" else self.warning
