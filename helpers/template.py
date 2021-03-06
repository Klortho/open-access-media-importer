#!/usr/bin/env python
# -*- coding: utf-8 -*-

def page(authors, article_title, journal_title, date, article_url, \
    license_url, rights_holder, label, caption, pmid):
    license_templates = {
        'http://creativecommons.org/licenses/by/2.0': '{{cc-by-2.0}}',
        'http://creativecommons.org/licenses/by-sa/2.0': '{{cc-by-sa-2.0}}',
        'http://creativecommons.org/licenses/by/2.5': '{{cc-by-2.5}}',
        'http://creativecommons.org/licenses/by/2.5/': '{{cc-by-2.5}}',
        'http://creativecommons.org/licenses/by-sa/2.5': '{{cc-by-sa-2.5}}',
        'http://creativecommons.org/licenses/by/3.0': '{{cc-by-3.0}}',
        'http://creativecommons.org/licenses/by-sa/3.0': '{{cc-by-sa-3.0}}'
    }
    license_template = license_templates[license_url]

    text = "=={{int:filedesc}}==\n\n"
    text += "{{Information\n"
    text += "|Description=\n{{en|%s}}\n" % caption
    text += "|Date= %s\n" % date
    text += "|Source= %s from %s, %s. PMID %s. Available from %s\n" % \
        (label, article_title, journal_title, pmid, article_url)
    text += "|Author= %s\n" % authors
    text += "|Permission= %s Copyright owner: %s\n" % \
        (license_template, rights_holder)
    text += "}}\n\n"
    text += "[[Category:Open Access Media Importer]]"
    return text
