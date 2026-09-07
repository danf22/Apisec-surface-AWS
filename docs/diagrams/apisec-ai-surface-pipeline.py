# Source for docs/diagrams/apisec-ai-surface-pipeline.png
# Rendered via the kiro-powers-diagrams power (diagrams-mcp engine).
# Requires the `diagrams` library and Graphviz if rendering locally:
#   pip install diagrams   (and: brew install graphviz)
#   python docs/diagrams/apisec-ai-surface-pipeline.py

from diagrams import Diagram, Cluster, Edge
from diagrams.aws.devtools import Codepipeline, Codebuild
from diagrams.aws.storage import S3
from diagrams.aws.security import IAMRole
from diagrams.onprem.vcs import Github

with Diagram("APIsec AI-Surface Scanning Pipeline", show=False, direction="LR"):
    gh = Github("GitHub repo\n(target source)")

    with Cluster("AWS - CodePipeline"):
        pipeline = Codepipeline("Pipeline")
        with Cluster("ScanAndPublish stage"):
            build = Codebuild("AI-Surface scan\n(CodeBuild)")
        role = IAMRole("CodeBuild role")

    artifacts = S3("Artifact bucket")
    reports = S3("Report bucket\n(static website)")

    gh >> Edge(label="CodeStar connection") >> pipeline
    pipeline >> Edge(label="source zip") >> artifacts
    pipeline >> build
    build >> role
    build >> Edge(label="HTML / JSON / SARIF / AI-BOM") >> reports
