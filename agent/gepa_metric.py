import dspy
import json
from typing import Any, Dict

class AssessAgentTrajectory(dspy.Signature):
    """Assess if the agent successfully achieved the user's goal based on its trajectory."""
    user_query = dspy.InputField(desc="The original task requested by the user")
    agent_trajectory = dspy.InputField(desc="The sequence of thoughts, tool calls, and final response from the agent")
    assessment_score = dspy.OutputField(desc="A score from 0.0 to 1.0 indicating how perfectly the agent achieved the goal. 1.0 is perfect, 0.0 is complete failure.")

def gepa_metric(example: dspy.Example, pred: dspy.Example, trace=None) -> float:
    """
    Pareto Front Metric for GEPA (Genetic Evolution of Prompt+Agent).
    Evaluates based on:
    - Accuracy: DSPy LLM judge score on the final trajectory (0.0 to 1.0)
    - Cost: Number of tool calls and tokens (fewer is better)
    - Latency: Number of agent turns (fewer is better)
    """
    # 1. Parse prediction trajectory (pred should contain the generated trajectory from the agent)
    # For DSPy, pred will usually be the output of our DSPy module (the new trajectory)
    # If pred is just a text output, we measure the length.
    
    trajectory = pred.get("trajectory", "")
    
    # 2. Accuracy Score
    # We use a DSPy judge to score the trajectory
    judge = dspy.Predict(AssessAgentTrajectory)
    try:
        result = judge(user_query=example.user_query, agent_trajectory=str(trajectory))
        accuracy = float(result.assessment_score)
    except Exception:
        accuracy = 0.0
        
    # Cap accuracy to 1.0
    accuracy = min(max(accuracy, 0.0), 1.0)
    
    # 3. Cost & Latency Penalties
    # We use string proxies for cost/latency since we might just have the raw text trajectory
    num_tool_calls = str(trajectory).count("<tool_call>")
    num_turns = str(trajectory).count("<think>")
    
    # Pareto weighting: We want high accuracy, but penalize excessive turns/cost.
    # Base accuracy is the primary driver. If accuracy is 0, score is 0.
    if accuracy < 0.5:
        return accuracy
        
    # Small penalty for each tool call and turn to encourage efficiency
    # E.g., -0.01 per tool call, -0.05 per turn
    penalty = (num_tool_calls * 0.01) + (num_turns * 0.02)
    
    final_score = accuracy - penalty
    return max(final_score, 0.0)
