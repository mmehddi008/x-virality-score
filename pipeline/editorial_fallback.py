"""Reviewed evergreen suggestions, explicitly labelled; never pretend to be AI analysis."""
import re

# shortcut: bounded editorial library; replace with healthy AI generation for broader daily variety.
LIBRARY = {
 'o2co': [
  ('web data scrape scraping agent', 'Freshness', 'A fresh response is not always fresh data. Before feeding scraped pages into an AI workflow, track when the source changed, when you collected it, and what your parser actually extracted.'),
  ('proxy proxies ip infrastructure', 'Useful responses', 'A proxy request can succeed while your scraper fails. Check the expected page content, schema and locale before counting a response as useful data.'),
  ('web data scrape scraping agent', 'Validation', 'Your scraper is part of your data quality system. Validate required fields, flag unexpected empty results, and keep the last known good output when a source changes.'),
  ('proxy proxies ip infrastructure', 'Session design', 'Choose proxy rotation around the workflow. Independent page fetches and multi-step sessions have different needs. Test session continuity before changing your routing strategy.'),
  ('web data scrape scraping agent', 'Failure visibility', 'A reliable scraping pipeline makes failures visible. Separate connection errors, unexpected pages and parsing failures so you can fix the layer that actually broke.'),
  ('web data scrape scraping agent', 'Source lineage', 'An AI answer is easier to trust when its inputs are traceable. Keep source URLs and collection timestamps alongside extracted data, then check whether the answer still matches the source.'),
  ('proxy proxies ip infrastructure', 'Benchmark design', 'Test a proxy with your actual workload: target pages, regions, session length and concurrency. A fast response on an easy page tells you little about a complex collection job.'),
  ('web data scrape scraping agent', 'Retry discipline', 'Retries should recover from temporary failures, not hide a broken parser. Use bounded retries, backoff and a clear stop condition when collecting web data.'),
  ('web data scrape scraping agent', 'Change detection', 'If every record suddenly loses the same field, investigate the page before trusting the dataset. A small layout change can look like a large business change.'),
  ('proxy proxies ip infrastructure', 'Geo checks', 'A successful connection does not confirm the right regional page. Check currency, language and location cues when your scraping workflow depends on geography.'),
  ('web data scrape scraping agent', 'Small pilots', 'Before scaling a scraping job, inspect a small sample end to end. The question is not just whether requests finish, but whether the resulting records answer your actual question.'),
  ('web data scrape scraping agent', 'Monitoring', 'Monitor useful records, not just completed requests. Empty pages, duplicate rows and missing fields can quietly turn an apparently healthy scraping job into unreliable data.'),
 ],
 'bitoff': [
  ('gift card crypto shopping', 'Region checks', 'Before buying a gift card with crypto, check the country, currency and eligible storefront. A familiar brand name does not guarantee that the card works with your account.'),
  ('gift card crypto shopping', 'Checkout checklist', 'A gift card purchase starts before checkout: confirm the retailer, region, redemption rules and final total. Keep the receipt until the balance is safely in your account.'),
  ('gift card crypto shopping', 'Network checks', 'When paying with crypto, match the asset and network to the payment instructions. Similar names are not interchangeable. Review the destination and amount before confirming.'),
  ('gift card crypto shopping', 'Redemption first', 'Read the redemption instructions before buying a gift card, not after. Account restrictions and regional rules can matter just as much as the card balance.'),
  ('gift card crypto shopping', 'Full cost', 'Compare the final checkout total, not only the advertised gift card value. Payment fees and retailer restrictions can change whether a purchase makes sense for you.'),
  ('gift card crypto shopping', 'Code privacy', 'Treat a gift card code like cash. Redeem through the official retailer flow and keep the code out of screenshots, public posts and unsolicited support conversations.'),
  ('gift card crypto shopping', 'Refund rules', 'Before paying with crypto, read both the seller refund policy and the retailer redemption terms. Buying a card and spending its balance are separate steps with separate rules.'),
  ('gift card crypto shopping', 'Right storefront', 'Shopping on Amazon or eBay? Check the exact regional storefront and its accepted payment methods before buying anything intended to fund the order.'),
  ('gift card crypto shopping', 'Payment records', 'Keep the order reference and transaction receipt together when shopping with crypto. Clear records make it easier to explain a payment issue without sharing private wallet information.'),
  ('gift card crypto shopping', 'Budget first', 'Start with what you plan to buy, then choose how to pay. A gift card is useful when it fits the purchase, the storefront and your budget.'),
  ('gift card crypto shopping', 'Gift suitability', 'Giving someone a digital gift card? Check which regional account they use and where they can redeem it. The most useful gift is one they can actually spend.'),
  ('gift card crypto shopping', 'Confirmation', 'A payment confirmation and a redeemed gift card are different milestones. Follow the order instructions through delivery and redemption, and save the relevant receipts.'),
 ]}

def prepare(slug, posts, previous):
    candidates = []
    for words, title, text in LIBRARY.get(slug, []):
        matches = [p for p in posts if set(words.split()) & set(re.findall(r'[a-z]+', p['text'].lower()))]
        if matches and text not in previous:
            candidates.append(dict(title=title, text=text, visual='A simple checklist illustrating '+title.lower()+'.',
                                   source_urls=[matches[0]['url']]))
    if len(candidates)<4:
        raise ValueError('Not enough relevant unused editorial suggestions; retain last-good data')
    return dict(summary='Editorial fallback: the configured AI provider was unavailable. These are reviewed evergreen suggestions matched to fresh source keywords, not AI-generated trend analysis. Source links indicate topic relevance, not endorsement or verified product claims.',
                analyses={p['url']:'Public source evidence retained for human review. Keyword matching was used for editorial suggestions; no automatic factual interpretation was performed.' for p in posts},
                drafts=candidates[:4])
