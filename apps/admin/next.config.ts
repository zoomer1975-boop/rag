import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  basePath: "/rag/admin",
  output: "standalone",
  async rewrites() {
    // nginx 없이 직접 배포 시 /rag/static/, /rag/widget/ 요청을 API 서버로 프록시
    const apiBase = process.env.INTERNAL_API_URL ?? "http://api:8000";
    return [
      {
        source: "/rag/static/:path*",
        destination: `${apiBase}/rag/static/:path*`,
      },
      {
        source: "/rag/widget/:path*",
        destination: `${apiBase}/widget/:path*`,
      },
    ];
  },
  transpilePackages: [
    "react-markdown",
    "remark",
    "remark-parse",
    "unified",
    "bail",
    "is-plain-obj",
    "trough",
    "vfile",
    "vfile-message",
    "unist-util-stringify-position",
    "mdast-util-from-markdown",
    "mdast-util-to-string",
    "micromark",
    "micromark-core-commonmark",
    "micromark-factory-destination",
    "micromark-factory-label",
    "micromark-factory-space",
    "micromark-factory-title",
    "micromark-factory-whitespace",
    "micromark-util-character",
    "micromark-util-chunked",
    "micromark-util-classify-character",
    "micromark-util-combine-extensions",
    "micromark-util-decode-numeric-character-reference",
    "micromark-util-encode",
    "micromark-util-html-tag-name",
    "micromark-util-normalize-identifier",
    "micromark-util-resolve-all",
    "micromark-util-sanitize-uri",
    "micromark-util-subtokenize",
    "micromark-util-symbol",
    "micromark-util-types",
    "decode-named-character-reference",
    "character-entities",
    "mdast-util-to-hast",
    "mdast-util-definitions",
    "trim-lines",
    "unist-util-is",
    "unist-util-visit",
    "unist-util-visit-parents",
    "hast-util-to-jsx-runtime",
    "comma-separated-tokens",
    "hast-util-whitespace",
    "property-information",
    "space-separated-tokens",
    "devlop",
    "estree-util-is-identifier-name",
    "hast-util-is-element",
    "html-url-attributes",
  ],
};

export default nextConfig;
