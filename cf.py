#!/usr/bin/env python3

import os
import sys
import requests
import base64
from rich.console import Console
from rich.progress import Progress
from io import BytesIO

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
        # Step 1: Generate images with OpenAI
        task1 = progress.add_task("[cyan]Generating images...", total=1)
        openai_headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        }
        openai_data = {
            "prompt": description,
            "n": 2,  # Generate 2 images
            "size": "1024x1024",
            "response_format": "b64_json",  # Return base64-encoded images
        }
        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers=openai_headers,
            json=openai_data,
        )
        response.raise_for_status()
        image_b64_list = [item["b64_json"] for item in response.json()["data"]]
        progress.update(task1, advance=1)

        # Step 2: Decode base64 to bytes
        image_data_list = [base64.b64decode(b64) for b64 in image_b64_list]

        # Step 3: Upload images to Cloudflare
        task2 = progress.add_task("[cyan]Uploading to Cloudflare...", total=2)
        cloudflare_headers = {"Authorization": f"Bearer {cloudflare_api_token}"}
        uploaded_urls = []

        for image_data in image_data_list:
            file_like = BytesIO(image_data)
            files = {"file": ("image.png", file_like, "image/png")}
            response = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/images/v1",
                headers=cloudflare_headers,
                files=files,
            )
            response.raise_for_status()
            image_url = response.json()["result"]["variants"][0]
            uploaded_urls.append(image_url)
            progress.update(task2, advance=1)

    # Step 4: Display the URLs
    console.print("[bold green]Generated Image URLs:[/bold green]")
    for i, url in enumerate(uploaded_urls, 1):
        console.print(f"Image {i}: {url}")

except requests.exceptions.RequestException as e:
    console.print(f"[bold red]Network Error: {e}[/bold red]")
except Exception as e:
    console.print(f"[bold red]Unexpected Error: {e}[/bold red]")
    sys.exit(1)
