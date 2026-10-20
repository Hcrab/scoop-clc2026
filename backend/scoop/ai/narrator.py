"""Turns structured findings into planner-facing language.

``scripted`` mode fills templates from the same structured evidence a language model would
receive. A model provider can replace :func:`explain_finding` without changing callers.
Every number in the text comes from the evidence dict, never from the model.
"""

from __future__ import annotations

DISPLAY = {
    "family": "{} family",
    "format": "{}s",
    "feature": "{}",
    "health": "{} claim",
    "flavour": "{} flavour",
}
PRETTY = {
    "Choc Coated": "Chocolate-coated",
    "Low Sugar": "Low-sugar",
    "Plant Based": "Plant-based",
    "High Protein": "High-protein",
    "Coffee Nut": "Coffee and nut",
    "Fruit Pieces": "Fruit pieces",
    "Stick": "Ice bar",
    "Multipack": "Multipack",
}
LABELS = {
    "persistent": "Persistent shift",
    "one_off": "Temporary event",
    "data_issue": "Data check needed",
    "weather": "Weather-related change",
    "mirror": "Possible shift elsewhere",
    "unsure": "Unclear",
}


def group_display(group_id: str, name: str) -> str:
    if group_id.startswith("band:"):
        return name
    dim = group_id.split(":")[0]
    pretty = PRETTY.get(name, name)
    return DISPLAY.get(dim, "{}").format(pretty)


def cohort_display(tag_path, groups, districts) -> str:
    """Compose a cohort label from its actual dimensions, independent of findings.

    Flavours are ordinary catalog data. Base and format nouns are generic English
    presentation mappings, never a lookup of a particular product or demo cohort.
    """
    priority = {'price_hkd': 0, 'price_100ml': 0, 'flavour': 1,
                'family': 2, 'feature': 3, 'health': 4, 'dairy': 5, 'format': 6}
    parts = []
    for step in tag_path:
        identifier = step['id']
        if not step['included'] or identifier.startswith('district:'):
            continue
        group = groups.get(identifier)
        dimension = getattr(group, 'dimension', identifier.split(':')[1] if identifier.startswith('band:') else identifier.split(':')[0])
        name = getattr(group, 'name', identifier.rsplit(':', 1)[-1].replace('_', ' ').title())
        parts.append((dimension, group_display(identifier, name)))
    parts.sort(key=lambda part: (priority.get(part[0], 4), part[1]))
    has_format = any(dimension == 'format' for dimension, _ in parts)
    # A format is the most specific noun; a dairy band supplies the noun otherwise.
    base_nouns = {'Water-based': 'water ices', 'Mixed': 'mixed-dairy ice creams',
                  'Creamy': 'creamy ice creams'}
    format_nouns = {'Sandwichs': 'sandwiches', 'Mochis': 'mochi'}
    adjectives, nouns = [], []
    for dimension, label in parts:
        if dimension == 'format':
            nouns.append(format_nouns.get(label, label.lower()))
        elif dimension == 'dairy' and not has_format and label in base_nouns:
            nouns.append(base_nouns[label])
        elif dimension == 'flavour':
            adjectives.append(label.removesuffix(' flavour').lower())
        elif dimension in ('price_hkd', 'price_100ml'):
            adjectives.append(label.lower().replace(' price', '-price'))
        else:
            adjectives.append(label.lower())
    name = ' '.join(adjectives + (nouns or ['products']))
    if any(not step['included'] for step in tag_path):
        name = 'Other ' + name
    elif not tag_path:
        name = 'All products'
    else:
        name = name[:1].upper() + name[1:]
    if any(step['id'].startswith('district:') for step in tag_path):
        name += ' · ' + ', '.join(districts)
    return name


def explain_finding(f: dict) -> str:
    name = f["display"]
    where = ", ".join(f["districts"])
    move = "an earlier rise" if f["direction"] == "up" else "an earlier decline"
    share = f"share {f['share_now']:.1%} vs {f['share_expected']:.1%} expected"
    since = f"since {f['alarm_date']:%d %b}" if f.get("alarm_date") is not None else ""
    lead = f"{name} triggered {move} in {where} ({share}) {since}.".replace("  ", " ")
    label = f["classification"]
    checks = {c["name"]: c for c in f["checks"]}
    if label == "persistent":
        body = (
            f"{checks['spread']['detail']}, and it is still there: {checks['persistence']['detail'].lower()}. "
            "A lasting change is one interpretation; these checks do not establish its cause."
        )
        if checks.get('record_heat',{}).get('passed'):
            body += " " + checks['record_heat']['detail'] + ". Heat remains a possible contributor."
    elif label == "one_off" and checks["promotion"]["passed"]:
        body = f"{checks['promotion']['detail']}. Check whether the change fades after the promotion ends."
    elif label == "one_off":
        body = f"{checks['persistence']['detail']}. Recent evidence is less consistent with a lasting change; keep the temporary-event interpretation under review."
    elif label == "data_issue":
        body = f"{checks['concentration']['detail']}. Review the concentrated store-day records before changing purchases; this does not establish an erroneous individual order."
    elif label == "weather":
        body = f"{checks['record_heat']['detail']}. These temperatures exceed the training range; weather is a plausible contributor whose effect is uncertain."
    elif label == "mirror":
        body = f"{checks['own_units']['detail']}. A change elsewhere may explain part of the share movement; this is a hypothesis to review."
    else:
        body = "The checks do not point to one cause yet; keep watching."
    mix = f["effect_mix"]
    vol = f["effect_volume"]
    split = (
        f" Descriptive breakdown: {mix:+,.0f} units/week associated with the changed demand mix, {vol:+,.0f} with overall demand. This arithmetic does not identify customer switching."
        if abs(mix) + abs(vol) > 0 else ""
    )
    return f"{lead} {body}{split}"


def question_for(f: dict) -> dict:
    name = f["display"]
    move = "earlier rise" if f["direction"] == "up" else "earlier decline"
    rec = f["classification"]
    options = [
        {"value": "persistent", "label": "Treat as persistent"},
        {"value": "watch", "label": "Watch one more week"},
        {"value": "one_off", "label": "Ignore (one-off)"},
    ]
    default = "persistent" if rec == "persistent" else "one_off" if rec in ("one_off", "data_issue", "mirror") else "watch"
    return {
        "text": f"{name} {move} in {', '.join(f['districts'])}: the evidence points to \"{LABELS[rec]}\". How should Scoop plan for it?",
        "options": options,
        "recommended": default,
    }


def saved_explanation(finding) -> str:
    """Present immutable saved facts without repeating old causal overclaims."""
    evidence=finding.evidence or {}
    checks=evidence.get('checks',[])
    required={'spread','persistence','promotion','concentration','record_heat','own_units'}
    if finding.kind!='significant' or not required.issubset({c['name'] for c in checks}):
        return 'This is an exploratory change to review against the saved measurements. Its cause is not established.'
    return explain_finding({'display':evidence.get('display',finding.tag_id),
        'districts':evidence.get('districts',finding.district.split(', ')),
        'direction':finding.direction,'share_now':finding.share_now,'share_expected':finding.share_before,
        'alarm_date':finding.alarm_date,'classification':finding.classification,
        'checks':checks,'effect_mix':finding.effect_mix,'effect_volume':finding.effect_volume})


def chat_reply(message: str, context: dict) -> str:
    """Scripted assistant for the four demo scenarios; falls back to a helpful summary."""
    m = message.lower()
    findings = context.get("findings", [])
    top = findings[0] if findings else None
    if any(k in m for k in ("why", "explain", "cause")) and top:
        return top["explanation"] + " Open the finding to see each check and its numbers."
    if any(k in m for k in ("35", "hot", "heat", "temperature", "weather")):
        hot = context.get("heat_scenario")
        if hot:
            return (
                f"If next week averages {hot['tmax']:.0f}C, demand over the planning window rises about {hot['total_pct']:+.0%} overall "
                f"and {hot['water_pct']:+.0%} for water-based lines. That adds about {hot['extra_cases']:,} cases, "
                f"and {hot['capacity_note']}"
            )
        return "I can run a heat scenario once the plan has forecasts."
    if "watch" in m or "monitor" in m or "keep an eye" in m:
        return "Added a watch card for that. It compares the actual share each day with the expected range and turns amber when it drifts."
    if any(k in m for k in ("order", "how much", "cases", "buy")):
        n = context.get("orders_due", 0)
        return f"{n} SKUs are due for ordering this week. Each line shows expected sales, the stock needed and why it changed."
    if top:
        return f"This week Scoop found {len(findings)} changes. The largest: {top['explanation']}"
    return "Nothing unusual this week. Orders follow the normal forecast."
