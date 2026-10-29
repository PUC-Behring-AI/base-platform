output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Kubernetes API endpoint."
  value       = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64 CA of the API, for the caller's kubectl provider."
  value       = module.eks.cluster_certificate_authority_data
}

output "oidc_issuer" {
  description = "The cluster's OIDC issuer URL."
  value       = module.eks.cluster_oidc_issuer_url
}

output "storage_class" {
  description = "StorageClass the charts name (ReadWriteOnce, gp3, encrypted)."
  value       = local.storage_class
}

output "gateway_class" {
  description = "GatewayClass of Auto Mode's ALB Gateway controller, for the edge Gateway's gatewayClassName."
  value       = local.gateway_class
}

output "eso_role_arn" {
  description = "IAM role External Secrets Operator assumes through Pod Identity."
  value       = aws_iam_role.eso.arn
}
