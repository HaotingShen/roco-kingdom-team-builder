/**
 * rktb-locale-routing — CloudFront Function (cloudfront-js-2.0), viewer-request
 * on the DEFAULT behavior of distribution E1S4H9ALERPPY0.
 *
 * Replaces rktb-spa-routing as part of the bilingual URL refactor
 * (see bilingual-url-locale-refactor.md Section K):
 *   1. /api/*            → passthrough (defense; separate behavior anyway)
 *   2. anything with "." → passthrough (static assets, sitemap.xml, robots.txt)
 *   3. /en | /zh         → 301 to /en/ | /zh/  (trailing-slash canonical form)
 *   4. /en/* | /zh/*     → SPA rewrite to /index.html
 *   5. /                 → 302 to /en/ or /zh/ by Accept-Language (Vary, no-store)
 *   6. everything else   → 301 to /en/<same path>  (legacy URLs; SEO equity)
 *
 * Query strings are preserved on ALL redirects. This is load-bearing: shared
 * team links are /import?t=<payload> — the whole payload lives in the query
 * string. CloudFront does NOT auto-append the query string when a function
 * returns a response object (it does preserve it on request rewrites).
 */
function handler(event) {
    var request = event.request;
    var uri = request.uri;
    var headers = request.headers;

    // Values in event.request.querystring arrive still percent-encoded,
    // so plain concatenation is safe.
    function buildQS(qs) {
        var out = [];
        for (var k in qs) {
            var v = qs[k];
            if (v.multiValue) {
                for (var i = 0; i < v.multiValue.length; i++) {
                    out.push(k + '=' + v.multiValue[i].value);
                }
            } else if (v.value !== undefined) {
                out.push(k + '=' + v.value);
            }
        }
        return out.length ? '?' + out.join('&') : '';
    }
    var qs = buildQS(request.querystring);

    // 1. API requests untouched
    if (uri.startsWith('/api/')) return request;

    // 2. Static files (anything with a dot) untouched
    if (uri.includes('.')) return request;

    // 3. Bare locale roots → 301 to the trailing-slash canonical form
    if (uri === '/en' || uri === '/zh') {
        return {
            statusCode: 301,
            statusDescription: 'Moved Permanently',
            headers: {
                'location': { value: uri + '/' + qs },
                'cache-control': { value: 'public, max-age=3600' }
            }
        };
    }

    // 4. Locale-prefixed → SPA rewrite (query string auto-preserved on rewrites)
    if (uri.startsWith('/en/') || uri.startsWith('/zh/')) {
        request.uri = '/index.html';
        return request;
    }

    // 5. Root: content-negotiated redirect (302 — target varies per user)
    if (uri === '/') {
        var lang = 'en';
        var al = headers['accept-language'];
        if (al && al.value && al.value.toLowerCase().indexOf('zh') === 0) {
            lang = 'zh';
        }
        return {
            statusCode: 302,
            statusDescription: 'Found',
            headers: {
                'location': { value: '/' + lang + '/' + qs },
                'vary': { value: 'Accept-Language' },
                'cache-control': { value: 'no-store' }
            }
        };
    }

    // 6. Legacy unprefixed routes → permanent redirect, query string preserved
    return {
        statusCode: 301,
        statusDescription: 'Moved Permanently',
        headers: {
            'location': { value: '/en' + uri + qs },
            'cache-control': { value: 'public, max-age=3600' }
        }
    };
}
