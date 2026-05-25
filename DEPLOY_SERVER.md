# Deploy Zimbabwe ANPR To A Server

This deploys the phone capture system so your phone connects to a public server instead of your laptop.

## Files The Server Needs

Keep these files together:

```text
main.py
mobile_server.py
dashboard.py
owner_registry.py
requirements.txt
Dockerfile
vehicle_best.pt
plate_best.pt
```

The two `.pt` model files are required. Without them, detection will not run.

## Recommended Hosting

Use a GPU server if possible. Good choices:

- RunPod GPU Pod
- Vast.ai GPU instance
- Any VPS with NVIDIA GPU and CUDA

A CPU server can work for testing, but detection will be slower.

## Option A: RunPod Quick Setup

1. Create a RunPod account.
2. Start a GPU Pod using a PyTorch template.
3. Choose a GPU such as RTX 3090, RTX 4090, A10, T4, or L4.
4. Expose HTTP port `8090`.
5. Upload this project folder to the pod.
6. Open a terminal inside the pod.
7. Install requirements:

```bash
pip install -r requirements.txt
```

8. Start the server:

```bash
python mobile_server.py --host 0.0.0.0 --port 8090 --gpu-ocr
```

For a public server, use a simple access token:

```bash
ANPR_TOKEN=choose-a-strong-password python mobile_server.py --host 0.0.0.0 --port 8090 --gpu-ocr
```

When the phone page opens, enter that same token before detecting.

9. Open the public HTTP URL that RunPod gives you for port `8090`.

On your phone, open that same URL. You can now take/upload a photo and get the plate result from the server.

## Option B: Docker Setup

Build the Docker image:

```bash
docker build -t zim-anpr .
```

Run on CPU:

```bash
docker run --rm -p 8090:8090 zim-anpr
```

Run on NVIDIA GPU:

```bash
docker run --rm --gpus all -p 8090:8090 zim-anpr python mobile_server.py --host 0.0.0.0 --port 8090 --gpu-ocr
```

Run with an access token:

```bash
docker run --rm --gpus all -p 8090:8090 -e ANPR_TOKEN=choose-a-strong-password zim-anpr python mobile_server.py --host 0.0.0.0 --port 8090 --gpu-ocr
```

Then open:

```text
http://SERVER_IP:8090
```

## Server Firewall

Allow inbound traffic on port `8090`.

For Ubuntu:

```bash
sudo ufw allow 8090/tcp
```

## Important Security Note

Set `ANPR_TOKEN` when running the server. Anyone using the phone page must enter that token before upload detection works.

## Common Problems

If the phone page opens but detection fails:

- Check that `vehicle_best.pt` and `plate_best.pt` are in the same folder.
- Check that the server has enough RAM.
- Try CPU mode first by removing `--gpu-ocr`.
- Check the server terminal logs.

If the page does not open:

- Confirm the server process is still running.
- Confirm port `8090` is exposed by the host.
- Confirm firewall/security-group rules allow port `8090`.
