from __future__ import annotations


def tenth_man_prompt(proposition: str) -> str:
    return (
        "Assume this proposition is materially wrong: "
        f"{proposition}\n"
        "Construct the strongest credible countercase. Identify hidden shared "
        "assumptions, cheaper explanations, discriminating evidence, and a "
        "recommended action. Do not invent weak objections."
    )
