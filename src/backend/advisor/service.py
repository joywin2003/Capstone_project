"""Inject a provider callable when the capstone advisor is integrated.

The provider receives (question, analytical_context) and returns text. This adapter
handles failures; it does not claim a working OpenAI integration.
"""

from backend.errors import AdvisorError


class EnergyAdvisor:
    def __init__(self, provider=None):
        self.provider = provider

    def explain(self, question, analytical_context):
        if not isinstance(question, str) or not question.strip():
            raise AdvisorError('Enter an energy question')
        if self.provider is None:
            raise AdvisorError('Energy advisor is not configured yet')
        try:
            answer = self.provider(question, analytical_context)
        except (TimeoutError, ConnectionError) as exc:
            raise AdvisorError('Energy advisor is temporarily unavailable; try again later') from exc
        if not isinstance(answer, str) or not answer.strip():
            raise AdvisorError('Energy advisor returned an empty response')
        return answer
