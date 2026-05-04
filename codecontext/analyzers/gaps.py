"""Gap detection - finds missing policies, tests, validators, and middleware."""

from __future__ import annotations

from codecontext.models import CodeNode, FileSummary, NodeType, ProjectIndex, Risk


def detect_gaps(index: ProjectIndex) -> list[Risk]:
    risks: list[Risk] = []
    risks.extend(_missing_policies(index))
    risks.extend(_missing_tests_for_controllers(index))
    risks.extend(_routes_without_permission(index))
    risks.extend(_write_routes_without_validation(index))
    return risks


def _missing_policies(index: ProjectIndex) -> list[Risk]:
    risks = []
    policy_classes = set()
    model_classes = set()

    for f in index.files:
        for n in f.nodes:
            if n.node_type == NodeType.POLICY:
                name = n.name.replace("Policy", "")
                policy_classes.add(name)
            elif n.node_type == NodeType.MODEL:
                model_classes.add(n.name)

    missing = model_classes - policy_classes
    ignored = {"Sexo", "TutorStudent", "InternalNotificationRecipient", "PendingEmail",
               "ClosingReminder", "StaffClassroomAttendance", "AttendanceWindow"}

    for model in sorted(missing):
        if model in ignored:
            continue
        risks.append(Risk(
            severity="info",
            category="gap-no-policy",
            message=f"Model '{model}' has no Policy class",
            location=f"app/Policies/{model}Policy.php",
            detail=f"Create {model}Policy to authorize actions on {model}",
        ))

    return risks[:20]


def _missing_tests_for_controllers(index: ProjectIndex) -> list[Risk]:
    risks = []
    controller_classes = set()
    test_names = set()

    for f in index.files:
        for n in f.nodes:
            if n.node_type == NodeType.CONTROLLER:
                name = n.name.replace("Controller", "")
                controller_classes.add((name, n.name, f.file_path))
            elif n.node_type == NodeType.TEST:
                test_names.add(n.name)

    for short, full, path in sorted(controller_classes):
        test_patterns = [
            f"{full}Test",
            f"{short}Test",
            f"{full}FeatureTest",
            f"{short}FeatureTest",
        ]
        if not any(p in test_names for p in test_patterns):
            risks.append(Risk(
                severity="info",
                category="gap-no-test",
                message=f"Controller '{full}' has no test class",
                location=path,
            ))

    return risks[:20]


def _routes_without_permission(index: ProjectIndex) -> list[Risk]:
    risks = []
    auth_keywords = {"auth", "verified", "role:", "permission:", "role_or_permission:"}

    protected_routes = [
        r for r in index.routes
        if any(any(kw in mw.lower() for kw in auth_keywords) for mw in r.middleware)
    ]

    perm_keywords = {"permission:", "role_or_permission:"}
    routes_without_perm = []

    for route in protected_routes:
        has_perm = any(any(kw in mw.lower() for kw in perm_keywords) for mw in route.middleware)
        if not has_perm:
            ctrl = route.controller.split("\\")[-1] if "\\" in route.controller else route.controller
            routes_without_perm.append(f"{route.http_method} {route.uri} → {ctrl}@{route.method}")

    if routes_without_perm:
        risks.append(Risk(
            severity="info",
            category="gap-no-permission",
            message=f"{len(routes_without_perm)} authenticated routes without explicit permission check",
            location="",
            detail=f"First 5: {'; '.join(routes_without_perm[:5])}",
        ))

    return risks


def _write_routes_without_validation(index: ProjectIndex) -> list[Risk]:
    risks = []
    request_classes = set()

    for f in index.files:
        for n in f.nodes:
            if n.node_type == NodeType.REQUEST:
                request_classes.add(n.name)

    write_routes = [
        r for r in index.routes
        if r.http_method in ("POST", "PUT", "PATCH")
        and r.method not in ("__invoke", "anonymous", "_render")
        and r.controller != "Closure"
    ]

    unvalidated = []
    for route in write_routes:
        ctrl_short = route.controller.split("\\")[-1] if "\\" in route.controller else route.controller
        action = route.method
        expected_request = f"{ctrl_short.replace('Controller', '')}{action.capitalize()}Request"

        has_request = any(
            rq.lower().replace("request", "") in f"{ctrl_short}{action}".lower()
            for rq in request_classes
        )

        if not has_request:
            unvalidated.append(f"{route.http_method} {route.uri} → {ctrl_short}@{action}")

    if unvalidated:
        risks.append(Risk(
            severity="info",
            category="gap-no-formrequest",
            message=f"{len(unvalidated)} write routes without matching FormRequest",
            location="",
            detail=f"First 5: {'; '.join(unvalidated[:5])}",
        ))

    return risks
