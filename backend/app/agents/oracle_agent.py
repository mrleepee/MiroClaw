"""
Oracle Agent

Specialist agent powered by a locally-hosted calibrated forecasting model
(OpenForecaster-8B or equivalent). Oracle agents do not post on social
media — they are consulted by regular agents and produce periodic forecasts.

Satisfies: R11 (Oracle agents)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .miroclaw_agent import MiroClawAgent
from ..utils.logger import get_logger

logger = get_logger('miroclaw.oracle_agent')


class OracleAgent(MiroClawAgent):
    """Oracle agent for calibrated forecasting.

    Distinct from regular MiroClaw agents:
    - Does not post on social media
    - Has no persona or stance; position-neutral
    - Uses a separate forecasting model endpoint
    - Produces periodic calibrated probability estimates
    - Consulted by regular agents during Research phase
    """

    def __init__(
        self,
        agent_id: str,
        model_endpoint: str = None,
        model_name: str = None,
        api_key: str = None,
        **kwargs,
    ):
        # Oracles have a neutral, position-free persona
        super().__init__(
            agent_id=agent_id,
            entity_name=f"Oracle_{agent_id}",
            entity_type="oracle",
            persona=(
                "You are an Oracle agent. Your role is to produce calibrated "
                "probability estimates based on evidence from the knowledge graph. "
                "You do not advocate for any position. You provide statistical "
                "forecasts with reasoning. When you say 70%, it means 70%."
            ),
            is_oracle=True,
            **kwargs,
        )
        self.model_endpoint = model_endpoint
        self.model_name = model_name
        self._forecast_history: List[Dict[str, Any]] = []

    def forecast(
        self,
        question: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """Produce a calibrated probability estimate for a question.

        Args:
            question: The question to forecast.
            context: Relevant context from the knowledge graph.

        Returns:
            Dict with probability, reasoning, and confidence.
        """
        try:
            # Use the oracle model endpoint
            from openai import OpenAI

            client = OpenAI(
                api_key=self.model_endpoint.get("api_key", "sk-placeholder") if isinstance(self.model_endpoint, dict) else "sk-placeholder",
                base_url=self.model_endpoint.get("base_url", "http://localhost:8080/v1") if isinstance(self.model_endpoint, dict) else (self.model_endpoint or "http://localhost:8080/v1"),
            )

            model_name = self.model_endpoint.get("model", "openforecaster-8b") if isinstance(self.model_endpoint, dict) else (self.model_name or "openforecaster-8b")

            prompt = f"""Question: {question}

Context from knowledge graph:
{context if context else 'No specific context available.'}

Provide a calibrated probability estimate. Return JSON:
{{
    "probability": <float 0.0-1.0>,
    "reasoning": "<your reasoning>",
    "confidence": "<high/medium/low>"
}}"""

            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a calibrated forecasting model. Produce probability estimates with reasoning."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            import json
            result = json.loads(response.choices[0].message.content)

            return {
                "probability": result.get("probability", 0.5),
                "reasoning": result.get("reasoning", ""),
                "confidence": result.get("confidence", "medium"),
            }

        except Exception as e:
            logger.warning(f"Oracle forecast failed, using fallback: {e}")
            return {
                "probability": 0.5,
                "reasoning": f"Forecast unavailable: {str(e)[:100]}",
                "confidence": "low",
            }

    def produce_periodic_forecast(
        self,
        questions: List[str],
        round_num: int,
        context: str = "",
    ) -> List[Dict[str, Any]]:
        """Produce forecasts on core questions (every N rounds).

        Args:
            questions: Core simulation questions.
            round_num: Current round number.
            context: Graph state summary.

        Returns:
            List of forecast entries.
        """
        forecasts = []

        for question in questions:
            result = self.forecast(question, context)

            entry = {
                "oracle_id": self.agent_id,
                "round": round_num,
                "question": question,
                "probability": result["probability"],
                "reasoning": result["reasoning"],
                "confidence": result["confidence"],
                "timestamp": datetime.now().isoformat(),
            }
            forecasts.append(entry)
            self._forecast_history.append(entry)

        logger.info(
            f"Oracle {self.agent_id} produced {len(forecasts)} forecasts "
            f"for round {round_num}"
        )
        return forecasts

    def get_forecast_history(
        self,
        question: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get forecast history, optionally filtered by question."""
        if question:
            return [
                f for f in self._forecast_history
                if f["question"] == question
            ]
        return self._forecast_history

    def get_confidence_drift(self, question: str) -> List[Dict[str, Any]]:
        """Get confidence drift time series for a question."""
        history = self.get_forecast_history(question)
        return [
            {
                "round": f["round"],
                "probability": f["probability"],
                "timestamp": f["timestamp"],
            }
            for f in sorted(history, key=lambda x: x["round"])
        ]
