terraform {
  required_version = ">= 1.6"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = { Project = var.project, ManagedBy = "terraform" } }
}

data "aws_caller_identity" "me" {}

# ---------------------------------------------------------------- paquete
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/guardian.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc"]
}

# ---------------------------------------------------------------- secretos
# Solo se crean los contenedores; los valores se cargan por CLI (ver README)
# para que nunca queden en el estado de Terraform ni en el repositorio.
resource "aws_secretsmanager_secret" "webhook" { name = "${var.project}/webhook-secret" }
resource "aws_secretsmanager_secret" "github" { name = "${var.project}/github-token" }
resource "aws_secretsmanager_secret" "anthropic" { name = "${var.project}/anthropic-key" }

# ---------------------------------------------------------------- datos
resource "aws_dynamodb_table" "state" {
  name         = "${var.project}-state"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  attribute {
    name = "pk"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}

# ---------------------------------------------------------------- cola
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project}-jobs-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "jobs" {
  name                       = "${var.project}-jobs"
  visibility_timeout_seconds = 1800 # >= 6x el timeout del worker (recomendación AWS)
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

# ---------------------------------------------------------------- IAM
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "receiver" {
  name               = "${var.project}-receiver"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role" "worker" {
  name               = "${var.project}-worker"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "receiver_logs" {
  role       = aws_iam_role.receiver.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "worker_logs" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Mínimo privilegio: cada rol solo toca lo que necesita.
resource "aws_iam_role_policy" "receiver" {
  role = aws_iam_role.receiver.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.jobs.arn },
      { Effect = "Allow", Action = ["dynamodb:PutItem", "dynamodb:DeleteItem"], Resource = aws_dynamodb_table.state.arn },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.webhook.arn },
    ]
  })
}

resource "aws_iam_role_policy" "worker" {
  role = aws_iam_role.worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"], Resource = aws_sqs_queue.jobs.arn },
      { Effect = "Allow", Action = ["dynamodb:PutItem"], Resource = aws_dynamodb_table.state.arn },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [aws_secretsmanager_secret.github.arn, aws_secretsmanager_secret.anthropic.arn] },
    ]
  })
}

# ---------------------------------------------------------------- Lambdas
resource "aws_cloudwatch_log_group" "receiver" {
  name              = "/aws/lambda/${var.project}-receiver"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${var.project}-worker"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "receiver" {
  function_name    = "${var.project}-receiver"
  role             = aws_iam_role.receiver.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "guardian.receiver.handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 10
  memory_size      = 256
  environment {
    variables = {
      TABLE_NAME         = aws_dynamodb_table.state.name
      QUEUE_URL          = aws_sqs_queue.jobs.url
      WEBHOOK_SECRET_ARN = aws_secretsmanager_secret.webhook.arn
    }
  }
  depends_on = [aws_cloudwatch_log_group.receiver]
}

resource "aws_lambda_function" "worker" {
  function_name                  = "${var.project}-worker"
  role                           = aws_iam_role.worker.arn
  runtime                        = "python3.12"
  architectures                  = ["arm64"]
  handler                        = "guardian.worker.handler"
  filename                       = data.archive_file.lambda.output_path
  source_code_hash               = data.archive_file.lambda.output_base64sha256
  timeout                        = 300
  memory_size                    = 512
  reserved_concurrent_executions = 10 # tope de gasto ante ráfagas de pushes
  environment {
    variables = {
      TABLE_NAME               = aws_dynamodb_table.state.name
      GITHUB_TOKEN_SECRET_ARN  = aws_secretsmanager_secret.github.arn
      ANTHROPIC_KEY_SECRET_ARN = aws_secretsmanager_secret.anthropic.arn
      MODEL                    = var.model
      LLM_BLOCKING             = tostring(var.llm_blocking)
    }
  }
  depends_on = [aws_cloudwatch_log_group.worker]
}

resource "aws_lambda_event_source_mapping" "jobs" {
  event_source_arn        = aws_sqs_queue.jobs.arn
  function_name           = aws_lambda_function.worker.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
  scaling_config { maximum_concurrency = 5 }
}

# ---------------------------------------------------------------- API
resource "aws_apigatewayv2_api" "http" {
  name          = "${var.project}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "receiver" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.receiver.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.receiver.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 20
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.receiver.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}

# ---------------------------------------------------------------- alarmas
resource "aws_sns_topic" "alerts" { name = "${var.project}-alerts" }

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "${var.project}-dlq-no-vacia"
  alarm_description   = "Hay revisiones que fallaron 3 veces: revisar logs del worker."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "worker_errors" {
  alarm_name          = "${var.project}-worker-errores"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.worker.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 3
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.project
  dashboard_body = jsonencode({
    widgets = [
      { type = "metric", x = 0, y = 0, width = 12, height = 6, properties = {
        title = "Revisiones y bloqueos", region = var.region, stat = "Sum", period = 3600,
      metrics = [["PyGuardian", "Reviews"], [".", "Blocked"], [".", "LlmFailed"]] } },
      { type = "metric", x = 12, y = 0, width = 12, height = 6, properties = {
        title = "Hallazgos", region = var.region, stat = "Sum", period = 3600,
      metrics = [["PyGuardian", "Errors"], [".", "Warnings"], [".", "DiscardedLlmFindings"]] } },
    ]
  })
}
