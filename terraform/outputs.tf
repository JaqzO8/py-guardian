output "webhook_url" {
  description = "Pégala en GitHub → Settings → Webhooks (content type: application/json, evento: push)"
  value       = "${aws_apigatewayv2_api.http.api_endpoint}/webhook"
}

output "secret_arns" {
  value = {
    webhook   = aws_secretsmanager_secret.webhook.arn
    github    = aws_secretsmanager_secret.github.arn
    anthropic = aws_secretsmanager_secret.anthropic.arn
  }
}

output "dlq_url" { value = aws_sqs_queue.dlq.url }
