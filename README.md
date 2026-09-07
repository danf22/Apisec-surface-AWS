# APIsec AI-Surface scanning pipeline (AWS)

CloudFormation stack that runs [apisec-inc/AI-Surface](https://github.com/apisec-inc/AI-Surface)
against a target GitHub repository on AWS and publishes the resulting **web report**
to S3 so the security team can review the findings.

## How it works

![APIsec AI-Surface scanning pipeline architecture](docs/diagrams/apisec-ai-surface-pipeline.png)

<sub>Diagram source: [`docs/diagrams/apisec-ai-surface-pipeline.py`](docs/diagrams/apisec-ai-surface-pipeline.py)</sub>

```
GitHub repo ──(CodeStar connection)──▶ CodePipeline
                                          │
                                          ├─ Source stage: pull repo
                                          │
                                          └─ ScanAndPublish stage (CodeBuild):
                                                • pip install apisec-ai-surface
                                                • ai-surface scan . (markdown/json/sarif/cyclonedx)
                                                • build index.html report
                                                • upload to S3 reports bucket
                                                        │
                                                        ▼
                                          S3 static website  ──▶ Security team
```

- **CodePipeline** orchestrates the run. The Source stage pulls the target repo through
  an AWS **CodeStar/CodeConnections GitHub connection**; the ScanAndPublish stage invokes CodeBuild.
- **CodeBuild** installs `ai-surface`, scans the checked-out repo, generates an HTML report
  plus JSON / SARIF / CycloneDX AI-BOM evidence, and uploads them to the reports S3 bucket.
- **S3** hosts the report as a static website with a stable `latest/` URL.

### A note on CodeDeploy

You asked for CodePipeline, CodeBuild, **and** CodeDeploy. `ai-surface` is an offline
static-analysis scanner: it produces a report, it does not deploy a running application
to compute (EC2 / Lambda / ECS), which is what the **CodeDeploy service** exists for.
There is nothing to deploy to a deployment group in a scan-and-report flow, so wiring in
CodeDeploy would only add a no-op target.

The "deploy" in this pipeline is the **publication of the report to S3**, handled inside
CodeBuild. If you specifically need the CodeDeploy service for standardization/compliance
reasons (e.g. an S3-to-S3 CodeDeploy deployment group), let me know and it can be added as
a variant — but functionally it is not required here.

## Files

| File | Purpose |
|---|---|
| `template.yaml` | CloudFormation stack: buckets, IAM roles, CodeBuild, CodePipeline, connection. |
| `buildspec.yml` | CodeBuild steps: install, scan, build HTML, publish to S3. |

## Prerequisites

- AWS CLI configured with permissions to create IAM, S3, CodeBuild, CodePipeline, and CodeConnections resources.
- A GitHub account with access to the repositories you want to scan.

## Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name apisec-ai-surface \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      ProjectName=apisec-ai-surface \
      RepoOwner=apisec-inc \
      RepoName=AI-Surface \
      RepoBranch=main \
      FullRepositoryId=apisec-inc/AI-Surface \
      FailOn=never
```

### Authorize the GitHub connection (one-time)

If you did **not** pass an existing `ExistingConnectionArn`, the stack creates a new
connection in `PENDING` state. You must authorize it once:

1. Open the AWS console → **Developer Tools → Settings → Connections**.
2. Select the connection named `<ProjectName>-gh` and click **Update pending connection**.
3. Complete the GitHub OAuth/app authorization and grant access to the repos you want to scan.

Until this is done, the pipeline's Source stage cannot pull the repo. The connection ARN is
also shown in the stack's `ConnectionArn` output.

To reuse an already-authorized connection instead, pass its ARN:

```bash
--parameter-overrides ExistingConnectionArn=arn:aws:codeconnections:REGION:ACCOUNT:connection/xxxx ...
```

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `ProjectName` | `apisec-ai-surface` | Name prefix for all resources. |
| `RepoOwner` | — | GitHub org/user that owns the repo to scan. |
| `RepoName` | — | Repository name to scan. |
| `RepoBranch` | `main` | Branch to scan. |
| `FullRepositoryId` | — | `owner/name` for the source action. |
| `ExistingConnectionArn` | `""` | Reuse an existing connection; blank creates a new one. |
| `FailOn` | `never` | `never` \| `high` \| `critical` — severity that fails the build. Keep `never` so the report always publishes. |
| `ReportRetentionDays` | `365` | Retention for timestamped report objects. |

## Run a scan

The pipeline runs automatically when the source branch changes. To run on demand:

```bash
aws codepipeline start-pipeline-execution --name apisec-ai-surface-pipeline
```

## Where the security team reads reports

After deploy, the stack outputs the report URLs:

```bash
aws cloudformation describe-stacks --stack-name apisec-ai-surface \
  --query "Stacks[0].Outputs" --output table
```

- **`LatestReportUrl`** — stable, bookmarkable URL for the most recent scan (`/latest/index.html`).
- **`ReportWebsiteUrl`** — base website URL. Every scan is also kept immutably under
  `reports/<owner>/<name>/<timestamp>/index.html`.

Each report page links to the raw `report.json`, `report.sarif`, and `ai-bom.cyclonedx.json`
evidence next to it.

## Scanning multiple repositories

Each stack scans one repository. To scan several repos, deploy the stack once per repo with
a distinct `ProjectName`:

```bash
aws cloudformation deploy --template-file template.yaml \
  --stack-name ai-surface-service-a --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides ProjectName=ai-surface-service-a \
      RepoOwner=my-org RepoName=service-a FullRepositoryId=my-org/service-a \
      ExistingConnectionArn=arn:aws:codeconnections:...:connection/xxxx
```

Reusing one authorized `ExistingConnectionArn` across stacks avoids re-authorizing GitHub
each time. (A multi-repo, single-pipeline matrix variant can be built if you prefer one stack
for many repos — ask and it can be added.)

## Security notes

- The reports bucket is configured for **static website hosting with public read** so the
  security team can open the URL directly. If reports must stay internal, remove
  `ReportBucketPolicy` from `template.yaml` and front the bucket with **CloudFront + Origin
  Access Control**, or restrict the bucket policy by `aws:SourceVpce` / source IP.
- The scanner runs offline: it executes no code from the target repo, makes no network calls,
  and needs no credentials for the target app.
- Buckets use `DeletionPolicy: Retain`; deleting the stack leaves the buckets (and reports) in place.
```
