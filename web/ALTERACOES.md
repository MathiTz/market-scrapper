# Diferenças da origem
O projeto original em G: não foi alterado nesta preparação.

- Todos os componentes e app/globals.css copiados sem alteração.
- Raiz abre Market com demo; /demo reexporta a raiz.
- Rota SVG de encartes fictícios preservada, removendo apenas bloqueio por ambiente para a prévia funcionar também no build local; não acessa dados reais.
- lib/geocoding.ts mantém só o tipo AddressResult.
- /api/location retorna erro 501 explicativo; /api/session oferece estado desautenticado e erro de login explicativo.
- Configuração Next simplificada, sem banco, rede local original ou ambiente E2E.
- package.json reduzido às dependências de frontend e scripts de desenvolvimento, build, execução e tipos; lockfile derivado do original.
- next-env.d.ts regenerado pelo Next; tsconfig.json copiado.
- Backend, conectores, catálogo de coleta, banco, workers, credenciais e caches excluídos.
- Fotos reais e encartes eram fornecidos por dados/API, não por arquivos locais em public. URLs e disponibilidade devem ser fornecidos pelo backend destinatário.
- Painel completo permanece no código; demonstração executável cobre experiência pública e login.
- Documentação, capturas novas e inventário adicionados para o handoff.