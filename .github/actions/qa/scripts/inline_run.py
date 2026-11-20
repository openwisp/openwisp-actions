"""Limit executable inline workflow and composite action blocks."""

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

MAX_LINES = 5


def run_nodes(node):
    """Yield only step-level run values, excluding unrelated YAML keys."""
    if isinstance(node, MappingNode):
        for key, value in node.value:
            if (
                isinstance(key, ScalarNode)
                and key.value == "steps"
                and isinstance(value, SequenceNode)
            ):
                for step in value.value:
                    if isinstance(step, MappingNode):
                        for step_key, step_value in step.value:
                            if (
                                isinstance(step_key, ScalarNode)
                                and step_key.value == "run"
                            ):
                                yield step_value
            yield from run_nodes(value)
    elif isinstance(node, SequenceNode):
        for value in node.value:
            yield from run_nodes(value)


def check_inline_runs(root):
    workflows = root / ".github/workflows"
    actions = root / ".github/actions"
    paths = [*workflows.glob("*.yml"), *workflows.glob("*.yaml")]
    paths.extend(actions.glob("**/action.yml"))
    paths.extend(actions.glob("**/action.yaml"))
    failed = False
    for path in paths:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for node in run_nodes(yaml.compose(text)):
            if node.style in ("|", ">"):
                body = lines[slice(node.start_mark.line + 1, node.end_mark.line)]
            else:
                body = lines[slice(node.start_mark.line, node.end_mark.line + 1)]
            while body and not body[-1].strip():
                body.pop()
            if len(body) > MAX_LINES:
                print(
                    f"{path}:{node.start_mark.line + 1}: run block has {len(body)} lines (max {MAX_LINES})"
                )
                failed = True
    return int(failed)
