# DeployProvider & DomainProvider Interfaces

> Provider-abstracted hosting + domain contracts. Vercel is the default; Eva-hosted / Netlify / others implement the same contract.

## DeployProvider

```typescript
interface DeployProvider {
  deployLanding(input: DeployInput, tenantId: string): Promise<{ url: string; deploymentId: string }>;
  updateLanding(deploymentId: string, input: DeployInput, tenantId: string): Promise<{ url: string }>;
  setEnvVar(deploymentId: string, key: string, value: string, tenantId: string): Promise<void>;
}

interface DeployInput {
  projectPath: string;        // built static dir or project root
  entryPoint?: string;       // index.html for static
  env?: Record<string, string>;
  serverlessFunctions?: boolean;  // include /api routes
}
```

## DomainProvider

```typescript
interface DomainProvider {
  attachDomain(domain: string, deploymentId: string, tenantId: string): Promise<{ dnsRecords: DNSRecord[]; status: string }>;
  verifyDomain(domain: string, tenantId: string): Promise<{ verified: boolean }>;
}
```

## Implementations
- **VercelProvider** — uses Vercel API to create project, set env vars, deploy, attach domain.
- **EvaHostedProvider** — pplx.app subdomains via deploy_website/publish_website; simplest path (no client DNS needed).
- **NetlifyProvider** — (future).

## Resolution
`TenantConfig.deploy_provider` selects implementation. New clients default to `eva-hosted` for speed; upgrade to `vercel` + custom domain when they bring their own domain.

## Notes
- Credentials for deploy providers are platform-level (Mangotec-owned), not per-tenant.
- Each deploy writes an audit row (`tenant_id`, `deploymentId`, `url`, `timestamp`).
