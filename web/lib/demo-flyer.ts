import { localTime } from "@/lib/domain";

type FlyerSource = {
  id: string;
  title: string;
  retailer_id: string;
  retailer_name: string;
  valid_from: string;
  valid_until: string;
};

const escapeXml = (value: string) =>
  value.replace(
    /[<>&"']/g,
    (c) =>
      ({
        "<": "&lt;",
        ">": "&gt;",
        "&": "&amp;",
        '"': "&quot;",
        "'": "&apos;",
      })[c]!,
  );

// Isolated demo: only fictional flyers, with no access to real data.
export function demoFlyerSvg(flyer: FlyerSource, page: 1 | 2): string {
  const networkA = flyer.retailer_id === "demo-a";
  const price =
    page === 2 ? (networkA ? "6,90" : "7,40") : networkA ? "15,90" : "17,49";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1560" viewBox="0 0 1200 1560" role="img" aria-labelledby="title desc">
  <title id="title">Encarte fictício · ${escapeXml(flyer.retailer_name)}</title>
  <desc id="desc">Demonstração de um encarte em alta resolução. Todos os dados e preços são fictícios.</desc>
  <rect width="1200" height="1560" fill="#fff"/>
  <rect width="1200" height="104" fill="#ffe6a6"/>
  <g font-family="Arial, Helvetica, sans-serif" fill="#173d30">
    <text x="64" y="65" font-size="30" font-weight="700">DEMONSTRAÇÃO · TODOS OS DADOS SÃO FICTÍCIOS</text>
    <text x="64" y="207" font-size="42">${escapeXml(flyer.retailer_name)}</text>
    <text x="64" y="295" font-size="60" font-weight="700">${escapeXml(flyer.title)}</text>
    <text x="64" y="360" font-size="28">${escapeXml(localTime(flyer.valid_from).split(",")[0])} a ${escapeXml(localTime(flyer.valid_until).split(",")[0])} · período ilustrativo</text>
    <line x1="64" y1="414" x2="1136" y2="414" stroke="#dde6e1" stroke-width="2"/>
    <text x="64" y="510" font-size="28">MARCA EXEMPLO · EMBALAGEM DE ${page === 2 ? "1 KG" : "250 G"}</text>
    <text x="64" y="580" font-size="50" font-weight="700">${page === 2 ? "Arroz branco" : "Café torrado e moído"}</text>
    <text x="64" y="640" font-size="30">${page === 2 ? "Tipo 1" : "Tradicional"} · preço comum de exemplo</text>
    <text x="64" y="795" font-size="96" font-weight="700">R$ ${price}</text>
    <text x="64" y="855" font-size="27">Valor fictício por embalagem. Não é uma oferta real.</text>
    <line x1="64" y1="925" x2="1136" y2="925" stroke="#dde6e1" stroke-width="2"/>
    <text x="64" y="1010" font-size="36" font-weight="700">Seu apoio para consultar preços</text>
    <text x="64" y="1080" font-size="30">Compare condições, confira a origem e planeje sua lista.</text>
    <text x="64" y="1140" font-size="30">Este documento serve apenas para testar a interface.</text>
    <text x="64" y="1200" font-size="30">Nenhum produto ou preço foi publicado como real.</text>
    <rect x="64" y="1300" width="1072" height="150" rx="12" fill="#f6f8f7"/>
    <text x="100" y="1360" font-size="28" font-weight="700">MERCADO EM DIA · WIREFRAME</text>
    <text x="100" y="1410" font-size="26">Imagem vetorial de exemplo · pode ampliar sem perder nitidez</text>
  </g></svg>`;
}

const urls = new Map<string, string>();

/** A blob URL for a flyer page. The demo has no server to serve images, so each distinct image is made once. */
export function demoFlyerUrl(flyer: FlyerSource, page: 1 | 2): string {
  const svg = demoFlyerSvg(flyer, page);
  let url = urls.get(svg);
  if (!url) {
    url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    urls.set(svg, url);
  }
  return url;
}
