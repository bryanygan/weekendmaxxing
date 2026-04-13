"""Desktop notifications — sends OS-native toast notifications for new deals."""

import subprocess
import sys


def notify(title: str, message: str) -> None:
    """Send a desktop notification. Works on Windows, macOS, and Linux."""
    if sys.platform == "win32":
        _notify_windows(title, message)
    elif sys.platform == "darwin":
        _notify_macos(title, message)
    else:
        _notify_linux(title, message)


def _notify_windows(title: str, message: str) -> None:
    """Use PowerShell toast notification on Windows."""
    try:
        ps_script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType = WindowsRuntime] | Out-Null; "
            "$template = [Windows.UI.Notifications.ToastNotificationManager]::"
            "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            "$text = $template.GetElementsByTagName('text'); "
            f"$text[0].AppendChild($template.CreateTextNode('{title}')); "
            f"$text[1].AppendChild($template.CreateTextNode('{message}')); "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
            "[Windows.UI.Notifications.ToastNotificationManager]::"
            "CreateToastNotifier('Weekend Deal Hunter').Show($toast)"
        )
        subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, timeout=10,
        )
    except Exception as exc:
        print(f"[notify] Windows notification failed: {exc}")


def _notify_macos(title: str, message: str) -> None:
    """Use osascript on macOS."""
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            capture_output=True, timeout=10,
        )
    except Exception as exc:
        print(f"[notify] macOS notification failed: {exc}")


def _notify_linux(title: str, message: str) -> None:
    """Use notify-send on Linux."""
    try:
        subprocess.run(
            ["notify-send", title, message],
            capture_output=True, timeout=10,
        )
    except Exception as exc:
        print(f"[notify] Linux notification failed: {exc}")


def notify_deals(deals: list[dict]) -> None:
    """Send a summary notification for new deals found."""
    if not deals:
        return

    count = len(deals)
    best = deals[0]
    dest = best.get("destination", "Unknown")
    price = best.get("total_trip_cost", 0)
    score = best.get("score", 0)

    title = f"Weekend Deal Hunter: {count} new deal{'s' if count > 1 else ''}!"
    message = f"Best: {dest} for ${price:.0f} (score: {score})"

    if count > 1:
        others = ", ".join(d.get("destination", "") for d in deals[1:3])
        message += f"\nAlso: {others}"

    notify(title, message)
    print(f"[notify] Desktop notification sent: {count} deals")
