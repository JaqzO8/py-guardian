variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "py-guardian"
}

variable "model" {
  description = "Modelo de Claude usado por el agente"
  type        = string
  default     = "claude-sonnet-5-5"
}

variable "llm_blocking" {
  description = "false = los errores del LLM solo advierten; true = también bloquean"
  type        = bool
  default     = false
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "alert_email" {
  description = "Correo para alarmas (vacío = sin suscripción)"
  type        = string
  default     = ""
}
