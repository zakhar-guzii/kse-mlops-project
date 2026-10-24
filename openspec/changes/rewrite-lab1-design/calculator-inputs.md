# Replacement AWS Pricing Calculator inputs

Status: **prepared, not saved.** Saving creates a public share link, so it needs explicit approval after these inputs are reviewed. Until then `docs/design.md` §6.7 states that the replacement estimate is pending.

Settings: [AWS Pricing Calculator](https://calculator.aws/), US East (N. Virginia), USD, On-Demand, 730 hours/month. Rates read 2026-10-23 (see [cloud research §5.2](../../../docs/research/cloud-deployment-cost.md#52-live-unit-rates-and-reproducible-provenance)).

| Entry | Inputs | Expected USD/month (listed) |
|---|---|---:|
| EC2 core | m6a.xlarge, Linux, 730 h; 50 GB gp3, baseline IOPS/throughput; 1 public IPv4 730 h | 133.794 |
| EC2 burst (training month only) | m6a.xlarge 20 h; 50 GB gp3 prorated 20/730; 1 IPv4 20 h | 3.666 |
| EC2 GPU (training month only) | g6.xlarge 40 h; 100 GB gp3 prorated 40/730; 1 IPv4 40 h | 32.830 |
| ECS | EC2 launch type, no additional fee; NAT gateways 0 | 0.000 |
| RDS for PostgreSQL | db.t4g.small, Single-AZ, 730 h; 20 GB gp3; backups within 20 GB; no CPU-credit overage | 25.660 |
| S3 Standard | 104 GB; 10,000 PUT/LIST; 100,000 GET | 2.482 |
| Data transfer out | 60 GB to internet, counted once | 5.400 |
| ECR | 5 GB private, same-region pulls | 0.500 |
| CloudWatch | 5 GB logs ingested and 5 GB stored; 5 custom metrics; 7 standard alarm metrics; 43,800 API requests | 5.288 |
| SNS / SES | 100 email deliveries and 100 publishes; 1000 SES emails | 0.102 |
| Route 53 | 1 hosted zone; 0.1 M standard queries; 1 HTTPS health check (AWS endpoint); `.com` $16/year entered separately as $1.333/month | 3.373 |
| Cognito / KMS | Essentials, 20 direct-sign-in MAU; AWS-managed keys, 10,000 symmetric requests | 0.330 |
| Bedrock | Claude Sonnet 5.5 global: 38.4 M input, 4.8 M output tokens (or 6000 calls × 6400 input / 800 output average); Titan Text Embeddings V2: 1.1 M tokens | 124.822 |

Reconciliation targets: steady month **$301.75** listed, **$289.23** after the $12.52005 recurring allowances (internet output 5.40, CloudWatch 5.288, health check 1.50, Cognito 0.30, KMS 0.03, SNS 0.00205); training month **$338.25** / **$325.73**. Growth case (2200 images and tasks; S3 108 GB with 22k/220k requests, 120 GB out, 11 GB logs, Bedrock 84.48 M / 10.56 M tokens): **$460.29 / $444.17** steady, **$496.79 / $480.67** training month.

If the calculator rounds hours or prorated disks differently, compare quantities and unit rates before treating a cent-level difference as a pricing discrepancy. Record whether the calculator applies the free allowances.
