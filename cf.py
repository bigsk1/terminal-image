#!/usr/bin/env python3

import os
import sys
import requests
import base64
import json
from datetime import datetime
from rich.console import Console
from rich.progress import Progress
from io import BytesIO
from PIL import Image

# Initialize Rich console for pretty terminal output
console = Console()

# Retrieve API keys from environment variables
openai_api_key = os.environ.get("OPENAI_API_KEY")
cloudflare_api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
cloudflare_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")

# Determine where to store history (same directory as script)
script_dir = os.path.dirname(os.path.abspath(__file__))
history_file = os.path.join(script_dir, "cf_history.json")

# Check if API keys are set
if not all([openai_api_key, cloudflare_api_token, cloudflare_account_id]):
    console.print(
        "[bold red]Error: Missing API keys or account ID. Please set OPENAI_API_KEY, "
        "CLOUDFLARE_API_TOKEN, and CLOUDFLARE_ACCOUNT_ID in your environment.[/bold red]"
    )
    sys.exit(1)

# Show history (ONLY JSON INFO, NO IMAGE PREVIEW)
if "--history" in sys.argv:
    if not os.path.exists(history_file):
        console.print("[bold yellow]No history found.[/bold yellow]")
    else:
        with open(history_file, "r") as f:
            history = json.load(f)
            console.print("[bold cyan]Past Image Generations:[/bold cyan]")
            for entry in history:
                console.print(f"[bold green]{entry['date']}[/bold green] - {entry['prompt']}")
                console.print(f"[bold blue]URL:[/bold blue] {entry['url']}")
                console.print(f"[bold magenta]Expiry:[/bold magenta] {entry['expiry']}\n")
    sys.exit(0)

# Display help menu
if "--help" in sys.argv:
    console.print("[bold cyan]Usage:[/bold cyan]")
    console.print("  python cf.py [--wide] [--expire 24h|30d] [--history] <image description>")
    console.print("\n[bold cyan]Options:[/bold cyan]")
    console.print("  --wide         Generate a wide image (1792x1024)")
    console.print("  --expire 24h   Set image to automatically expire after 24 hours")
    console.print("  --expire 30d   Set image to automatically expire after 30 days")
    console.print("  --history      Show past image generations (prompts, URLs, expiry status)")
    console.print("  --help         Show this help message")
    sys.exit(0)

# Detect options
is_wide = "--wide" in sys.argv
expire_time = None  # Default: No expiry

# Remove options from arguments
args = []
for i in range(len(sys.argv[1:])):
    if sys.argv[i + 1] == "--wide":
        continue
    elif sys.argv[i + 1] == "--expire":
        if i + 2 < len(sys.argv) and sys.argv[i + 2] in ["24h", "30d"]:
            expire_time = sys.argv[i + 2]
        continue
    args.append(sys.argv[i + 1])

# Ensure there is an image description
if len(args) < 1:
    console.print("[bold red]Error: Missing image description.[/bold red]")
    console.print("[bold yellow]Use --help for usage information.[/bold yellow]")
    sys.exit(1)

description = " ".join(args)

# Set image size
image_size = "1792x1024" if is_wide else "1024x1024"

# Main script logic
try:
    with Progress() as progress:
        # Step 1: Generate image with OpenAI (DALL-E 3)
        task1 = progress.add_task("[cyan]Generating image...", total=1)
        openai_headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        }
        openai_data = {
            "prompt": description,
            "n": 1,
            "size": image_size,
            "response_format": "b64_json",
            "model": "dall-e-3",
        }
        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers=openai_headers,
            json=openai_data,
        )
        response.raise_for_status()
        image_b64 = response.json()["data"][0]["b64_json"]
        progress.update(task1, advance=1)

        # Step 2: Decode base64 to bytes
        image_data = base64.b64decode(image_b64)

        # Step 3: Upload image to Cloudflare with or without expiry
        task2 = progress.add_task("[cyan]Uploading to Cloudflare...", total=1)
        cloudflare_headers = {"Authorization": f"Bearer {cloudflare_api_token}"}
        file_like = BytesIO(image_data)
        files = {"file": ("image.png", file_like, "image/png")}

        # Add expiry metadata correctly (Cloudflare requires a string, not None)
        cloudflare_data = {"metadata": {"expiry": expire_time or "none"}}


        response = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/images/v1",
            headers=cloudflare_headers,
            files=files,
            json=cloudflare_data
        )
        response.raise_for_status()
        image_url = response.json()["result"]["variants"][0]
        progress.update(task2, advance=1)

    # Step 4: Display the URL (formatted output for humans)
    console.print("[bold green]Generated Image URL:[/bold green]")
    console.print(f"[bold cyan]Image:[/bold cyan] {image_url}")

    # Show expiry message if applicable
    if expire_time:
        console.print(f"[bold yellow]Note: This image will expire in {expire_time}.[/bold yellow]")

    # Step 5: Restore Terminal Preview
    try:
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        image_data = image_response.content

        # Save it as a temporary file
        temp_image_path = "/tmp/cf_image.png"
        with open(temp_image_path, "wb") as f:
            f.write(image_data)

        # Resize the image for terminal preview
        image = Image.open(temp_image_path)

        # Maintain proper aspect ratio for square and wide images
        preview_width, preview_height = (80, 40) if is_wide else (60, 50)

        image = image.resize((preview_width, preview_height), Image.Resampling.LANCZOS)
        image.save(temp_image_path, format="PNG")

        # Display the image in the best available format
        if os.system("command -v kitten >/dev/null") == 0:
            os.system(f"kitten icat {temp_image_path}")
        elif os.system("command -v viu >/dev/null") == 0:
            os.system(f"viu -w {preview_width} {temp_image_path}")
        elif os.system("command -v chafa >/dev/null") == 0:
            os.system(f"chafa --size={preview_width}x{preview_height} --symbols=block {temp_image_path}")
        else:
            console.print("[yellow]Install 'kitten icat', 'viu', or 'chafa' for better image previews.[/yellow]")

    except requests.exceptions.RequestException as e:
        console.print(f"[bold red]Error displaying image: {e}[/bold red]")

    # Step 6: Save History (after preview)
    final_expiry = expire_time or "None"  # Ensure expiry is always a string

    history_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "prompt": description,
        "url": image_url,
        "expiry": final_expiry
    }

    # console.print(f"[bold yellow]DEBUG: History Entry - {history_entry}[/bold yellow]")  # Debugging line


    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            history = json.load(f)
    else:
        history = []

    history.append(history_entry)

    with open(history_file, "w") as f:
        json.dump(history, f, indent=4)

except Exception as e:
    console.print(f"[bold red]Unexpected Error: {e}[/bold red]")
    sys.exit(1)
