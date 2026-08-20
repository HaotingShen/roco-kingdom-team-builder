# Production deploy script

`deploy.sh` is the script the GitHub Actions workflow invokes on the EC2 box, via SSM:

```
aws s3 cp s3://rktb-frontend/deploy/docker-compose.prod.yml /home/ubuntu/rktb/
bash /home/ubuntu/rktb/deploy.sh <git-sha>
```

## This file is NOT deployed automatically

`.github/workflows/deploy.yml` uploads **only** `docker-compose.prod.yml` to S3, which the
box then pulls down (overwriting its local copy). It never touches `deploy.sh`.

That means:

- The copy that actually runs in production is `/home/ubuntu/rktb/deploy.sh` on the instance.
- **Editing this repo copy does nothing until you manually copy it to the box.**
- Conversely, an on-box edit will not show up here, and would be lost if the instance were
  ever rebuilt.

Until 2026-08-20 this script existed *only* on the instance and was not version controlled
at all. This directory is that backup.

## Keeping the two in sync

The committed copy was taken from the box on 2026-08-20 and is byte-identical to what was
running at that time:

```
sha256  f71c8a0f1329ef8af5308f269414aa099a44a8cce2554acb31a532ba579c2719
```

Verify the box still matches:

```bash
aws ssm send-command --instance-ids i-08477110ddb42c54d \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["sha256sum /home/ubuntu/rktb/deploy.sh"]' \
  --region ap-southeast-1
```

To push a change to the box after editing here, copy it up and re-run the checksum to
confirm. Do not edit the on-box copy directly.

Why this matters: until it was committed here, a rebuild of the instance would have
lost the only copy of the production deploy script.
