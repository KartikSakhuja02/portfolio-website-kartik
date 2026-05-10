# AWS Deployment Steps

This project is set up to run on a single EC2 instance behind AWS networking, with real-time memory usage, request volume, and EC2 logs coming from the host.

## What the app expects

Set these environment variables on the EC2 host or in the Docker environment:

- `AWS_REGION`
- `AWS_EC2_INSTANCE_ID`
- `AWS_LB_NAME`
- `HOST_LOG_DIR`

For EC2 host logs, use:

- `HOST_LOG_DIR=/var/log`

For local development, the Compose file defaults to `./host-logs` so the app still runs without EC2 host mounts.

## AWS Console Setup

### 1. Create or choose an EC2 instance

- Open the EC2 console.
- Launch an Ubuntu 22.04 or Amazon Linux 2023 instance.
- Attach a key pair if you want SSH access.
- Use a security group that allows:
  - Port `22` only from your IP if you need SSH
  - Port `80` from the internet, or from an ALB if you place one in front
  - Port `443` from the internet, or from an ALB if you place one in front

### 2. Attach an IAM role

Attach an instance role with permissions for:

- `CloudWatchReadOnlyAccess` for dashboard metrics
- `AmazonSSMManagedInstanceCore` if you want Session Manager instead of SSH
- Any additional read permissions your app needs for AWS APIs

### 3. Set up the load balancer

If you want HTTPS and a public domain:

- Create an Application Load Balancer.
- Put the EC2 instance in a target group.
- Allow the ALB security group to reach the EC2 security group on the app port.
- Keep the EC2 instance port closed to the public if the ALB is in front.

### 4. Create an ACM certificate

If you want HTTPS:

- Open ACM.
- Request a public certificate for your domain.
- Validate it through DNS.
- Attach the certificate to the ALB listener on port `443`.

### 5. Create DNS records

If you use Route 53:

- Create an `A` or `AAAA` alias record for your domain.
- Point it to the ALB.
- If you are not using an ALB, point the record to the EC2 public IP, but HTTPS will still require a valid certificate setup.

## EC2 Host Setup

### 6. Install Docker and Compose

On the EC2 instance, install Docker and the Compose plugin or legacy Compose, depending on what the host supports.

### 7. Clone the repo

- SSH into the instance or use Session Manager.
- Clone your repository.
- Create or update the `.env` file.

### 8. Configure the runtime values

Set the runtime variables so the dashboard shows real data:

- `AWS_REGION` should match the region where your EC2 instance and ALB live.
- `AWS_EC2_INSTANCE_ID` should be the running instance ID.
- `AWS_LB_NAME` should match the load balancer name if you want CloudWatch request metrics.
- `HOST_LOG_DIR` should be `/var/log` on EC2.

### 9. Start the app

Use Compose on the instance:

```bash
HOST_LOG_DIR=/var/log docker compose up -d --build
```

If your host only supports legacy Compose or BuildKit has issues, use the same workaround you already used for the image build path.

## Verify in AWS

### 10. Check the app

- Open the public URL or ALB DNS name.
- Confirm CPU, memory, request volume, and logs update in the dashboard.
- Confirm the instance security group only exposes what you intend.

### 11. Check metrics and logs

- In CloudWatch, confirm EC2 CPU and ALB request metrics are visible.
- In the app, confirm memory usage is coming from the host runtime.
- In the app, confirm logs are showing recent EC2 host lines and application request lines.

## Notes

- The dashboard memory card reads from `/proc/meminfo` inside the EC2 host runtime.
- The request card falls back to live request counts when ALB metrics are unavailable.
- The logs panel reads from the EC2 host log mount, so `HOST_LOG_DIR=/var/log` is the important setting on the instance.
