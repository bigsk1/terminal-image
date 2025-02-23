#!/usr/bin/env python3

import os
import sys
import requests
import base64
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

# Check if API keys are set
if not all([openai_api_key, cloudflare_api_token, cloudflare_account_id]):
    console.print(
        "[bold red]Error: Missing API keys or account ID. Please set OPENAI_API_KEY, "
        "CLOUDFLARE_API_TOKEN, and CLOUDFLARE_ACCOUNT_ID in your environment.[/bold red]"
    )
    sys.exit(1)

# Parse the image description from command-line arguments
if len(sys.argv) < 2:
    console.print("[bold red]Usage: python cf.py <image description>[/bold red]")
    sys.exit(1)

description = " ".join(sys.argv[1:])

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
            "n": 1,  # DALL-E 3 only supports 1 image
            "size": "1024x1024",
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

        # Step 3: Upload image to Cloudflare
        task2 = progress.add_task("[cyan]Uploading to Cloudflare...", total=1)
        cloudflare_headers = {"Authorization": f"Bearer {cloudflare_api_token}"}
        file_like = BytesIO(image_data)
        files = {"file": ("image.png", file_like, "image/png")}
        response = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/images/v1",
            headers=cloudflare_headers,
            files=files,
        )
        response.raise_for_status()
        image_url = response.json()["result"]["variants"][0]
        progress.update(task2, advance=1)

    # Step 4: Display the URL
    console.print("[bold green]Generated Image URL:[/bold green]")
    console.print(f"Image: {image_url}")

    # Step 5: Download and resize the image for better terminal preview
    try:
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        image_data = image_response.content

        # Save it as a temporary file
        temp_image_path = "/tmp/cf_image.png"
        with open(temp_image_path, "wb") as f:
            f.write(image_data)

        # Resize the image using Pillow before displaying
        image = Image.open(temp_image_path)
        image = image.resize((200, 200), Image.Resampling.LANCZOS)  # High-quality downscaling
        image.save(temp_image_path, format="PNG")

        # Display the image in the best available format
        if os.system("command -v kitten >/dev/null") == 0:
            os.system(f"kitten icat {temp_image_path}")  # Best quality (Kitty/WezTerm)
        elif os.system("command -v viu >/dev/null") == 0:
            os.system(f"viu -w 50 {temp_image_path}")  # Better color rendering
        elif os.system("command -v chafa >/dev/null") == 0:
            os.system(f"chafa --size=50x25 --symbols=block {temp_image_path}")  # High detail ASCII
        else:
            console.print("[yellow]Install 'kitten icat', 'viu', or 'chafa' for better image previews.[/yellow]")

    except requests.exceptions.RequestException as e:
        console.print(f"[bold red]Error displaying image: {e}[/bold red]")

except requests.exceptions.RequestException as e:
    # Enhanced error reporting
    console.print(f"[bold red]Network Error: {e}[/bold red]")
    if hasattr(e.response, 'text'):
        console.print(f"[red]Error Details: {e.response.text}[/red]")
except Exception as e:
    console.print(f"[bold red]Unexpected Error: {e}[/bold red]")
    sys.exit(1)
