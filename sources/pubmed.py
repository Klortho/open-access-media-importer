#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import date
from os import listdir, path
from urllib2 import urlopen, urlparse
from xml.etree.cElementTree import dump, ElementTree
# the C implementation of ElementTree is 5 to 20 times faster than the Python one

from hashlib import md5

import tarfile

# According to <ftp://ftp.ncbi.nlm.nih.gov/README.ftp>, this should be
# 33554432 (32MiB) for best performance. Note that on slow connections,
# however, huge buffers size leads to notable interface lag.
BUFSIZE = 33554432
#BUFSIZE = 1024000  # (1024KB)

def download_metadata(target_directory):
    """
    Downloads files from PMC FTP server into given directory.
    """
    urls = [
        'ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/articles.A-B.tar.gz',
        'ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/articles.C-H.tar.gz',
        'ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/articles.I-N.tar.gz',
        'ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/articles.O-Z.tar.gz'
    ]

    for url in urls:
        remote_file = urlopen(url)
        total = int(remote_file.headers['content-length'])
        completed = 0

        url_path = urlparse.urlsplit(url).path
        local_filename = path.join(target_directory, \
            url_path.split('/')[-1])

        # if local file has same size as remote file, skip download
        try:
            if (path.getsize(local_filename) == total):
                continue
        except OSError:  # local file does not exist
            pass

        with open(local_filename,'wb') as local_file:
            while True:
                chunk = remote_file.read(BUFSIZE)
                if chunk != '':
                    local_file.write(chunk)
                    completed += len(chunk)
                    yield {
                        'url': url,
                        'completed': completed,
                        'total': total
                    }
                else:
                    break

def list_articles(target_directory, supplementary_materials=False, skip=[]):
    """
    Iterates over archive files in target_directory, yielding article information.
    """
    listing = listdir(target_directory)
    for filename in listing:
        with tarfile.open(path.join(target_directory, filename)) as archive:
            for item in archive:
                if item.name in skip:
                    continue
                if path.splitext(item.name)[1] == '.nxml':
                    content = archive.extractfile(item)
                    tree = ElementTree()
                    tree.parse(content)

                    result = {}
                    result['name'] = item.name
                    result['article-contrib-authors'] = _get_article_contrib_authors(tree)
                    result['article-title'] = _get_article_title(tree)
                    result['article-abstract'] = _get_article_abstract(tree)
                    result['journal-title'] = _get_journal_title(tree)
                    result['article-date'] = _get_article_date(tree)
                    result['article-url'] = _get_article_url(tree)
                    result['article-license-url'] = _get_article_license_url(tree)
                    result['article-copyright-holder'] = _get_article_copyright_holder(tree)

                    if supplementary_materials:
                        result['supplementary-materials'] = _get_supplementary_materials(tree)
                    yield result

def _get_article_contrib_authors(tree):
    from sys import stderr
    """
    Given an ElementTree, returns article authors in a format suitable for citation.
    """
    authors = []
    front = ElementTree(tree).find('front')
    for contrib in front.iter('contrib'):
        contribTree = ElementTree(contrib)
        try:
            surname = contribTree.find('name/surname').text
        except AttributeError:  # author is not a natural person
            try:
                citation_name = contribTree.find('collab').text
                if citation_name is not None:
                    authors.append(citation_name)
                continue
            except AttributeError:  # name has no immediate text node
                continue

        try:
            given_names = contribTree.find('name/given-names').text
            citation_name = ' '.join([surname, given_names[0]])
        except AttributeError:  # no given names
            citation_name = surname
        except TypeError:  # also no given names
            citation_name = surname
        if citation_name is not None:
            authors.append(citation_name)

    return ', '.join(authors)

def _get_article_title(tree):
    """
    Given an ElementTree, returns article title.
    """
    title = ElementTree(tree).find('front/article-meta/title-group/article-title')
    if title is None:
        title = ElementTree(tree).find('front/article-meta/article-categories/subj-group/subject')
    return ' '.join(title.itertext())

def _get_article_abstract(tree):
    """
    Given an ElementTree, returns article abstract.
    """
    abstract = ElementTree(tree).find('front/article-meta/abstract')
    if abstract is not None:
        return ' '.join(abstract.itertext())
    else:
        return ''

def _get_journal_title(tree):
    """
    Given an ElementTree, returns journal title.
    """
    front = ElementTree(tree).find('front')
    for journal_meta in front.iter('journal-meta'):
        for journal_title in journal_meta.iter('journal-title'):
            return journal_title.text

def _get_article_date(tree):
    """
    Given an ElementTree, returns article date.
    """
    article_meta = ElementTree(tree).find('front/article-meta')
    for pub_date in article_meta.iter('pub-date'):
        if pub_date.attrib['pub-type'] == 'epub':
            pub_date_tree = ElementTree(pub_date)
            year = int(pub_date_tree.find('year').text)
            try:
                month = int(pub_date_tree.find('month').text)
            except AttributeError:
                month = 1 # TODO: is this correct?
            try:
                day = int(pub_date_tree.find('day').text)
            except AttributeError:
                day = 1  # TODO: is this correct?
            return str(date(year, month, day))
    return ''

def _get_article_url(tree):
    """
    Given an ElementTree, returns article URL.
    """
    article_meta = ElementTree(tree).find('front/article-meta')
    for article_id in article_meta.iter('article-id'):
        if article_id.attrib['pub-id-type'] == 'doi':
            return 'http://dx.doi.org/' + article_id.text
    return ''  # FIXME: this should never, ever happen

license_url_equivalents = {
    'This is an open access article distributed under the Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.' : 'http://creativecommons.org/licenses/by/3.0',
    'This is an open-access article distributed under the terms of the Creative Commons Attribution Non-commercial License, which permits use, distribution, and reproduction in any medium, provided the original work is properly cited, the use is non commercial and is otherwise in compliance with the license. See:  http://creativecommons.org/licenses/by-nc/2.0/  and  http://creativecommons.org/licenses/by-nc/2.0/legalcode .': 'http://creativecommons.org/licenses/by-nc/2.0/',
    'This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/2.0/uk/ ) which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.': 'http://creativecommons.org/licenses/by-nc/2.0/uk/',
    'This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/2.5/uk/ ) which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.': 'http://creativecommons.org/licenses/by-nc/2.5/uk/',
    'This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/2.5 ), which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.': 'http://creativecommons.org/licenses/by-nc/2.5',
    'This is an Open Access article which permits unrestricted noncommercial use, provided the original work is properly cited.': '',
    """Users may view, print, copy, download and text and data- mine the content in such documents, for the purposes of academic research, subject always to the full Conditions of use: 
 http://www.nature.com/authors/editorial_policies/license.html#terms""": 'http://www.nature.com/authors/editorial_policies/license.html#terms',  # TODO: Is this a free license?
    """Users may view, print, copy, download and text and data- mine the content in such documents, for the purposes of academic research, subject always to the full Conditions of use:
 http://www.nature.com/authors/editorial_policies/license.html#terms""": 'http://www.nature.com/authors/editorial_policies/license.html#terms',  # this statement is different
    """Users may view, print, copy, download and text and data- mine the content in such documents, for the purposes of academic research, subject always to the full Conditions of use:  http://www.nature.com/authors/editorial_policies/license.html#terms""": 'http://www.nature.com/authors/editorial_policies/license.html#terms',  # this statement, again, is different
    'This document may be redistributed and reused, subject to  certain conditions .': '',  # TODO: Which conditions?
    'This is an Open Access article distributed under the terms of the Creative Commons Attribution License (<url>http://creativecommons.org/licenses/by/2.0</url>), which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.': 'http://creativecommons.org/licenses/by/2.0',
    'This work is licensed under a Creative Commons Attribution 3.0 License (by-nc 3.0) Licensee PAGEPress, Italy': 'http://creativecommons.org/licenses/by-nc/3.0',
    'This work is licensed under a Creative Commons Attribution 3.0 License (by-nc 3.0). Licensee PAGEPress, Italy': 'http://creativecommons.org/licenses/by-nc/3.0',  # this statement is inconsistent
    'This work is licensed under a Creative Commons Attribution 3.0 License (by-nc 3.0). Licensee PAGE Press, Italy': 'http://creativecommons.org/licenses/by-nc/3.0',  # this statement is, again, inconsistent
    'This work is licensed under a Creative Commons Attr0ibution 3.0 License (by-nc 3.0). Licensee PAGE Press, Italy': 'http://creativecommons.org/licenses/by-nc/3.0',  # this statement is is inconsistent and contains a typo
    'This work is licensed under a Creative Commons Attribution NonCommercial 3.0 License (CC BY-NC 3.0). Licensee PAGEPress, Italy': 'http://creativecommons.org/licenses/by-nc/3.0',
    'This work is licensed under a Creative Commons Attribution NonCommercial 3.0 License (CC BY-NC 3.0). Licensee PAGEPress srl, Italy': 'http://creativecommons.org/licenses/by-nc/3.0',
    """This work is licensed under a Creative Commons Attribution 3.0
License (by-nc 3.0). Licensee PAGEPress, Italy""": 'http://creativecommons.org/licenses/by-nc/3.0',
    """>This work is licensed under a Creative Commons Attribution NonCommercial 3.0 License (CC BY-NC 3.0). Licensee PAGEPress, Italy""": 'http://creativecommons.org/licenses/by-nc/3.0',
    'This research note is distributed under the  Creative Commons Attribution 3.0 License.': 'http://creativecommons.org/licenses/by/3.0',
    """This research note is distributed under the  Creative Commons
						Attribution 3.0 License.""": 'http://creativecommons.org/licenses/by/3.0',
    """
           This research note is distributed under the  Creative Commons Attribution 3.0 License. 
        """: 'http://creativecommons.org/licenses/by/3.0',
    """This is an open access article distributed under the Creative
                                    Commons Attribution License, which permits unrestricted use,
                                    distribution, and reproduction in any medium, provided the
                                    original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the Creative Commons Attribution License, which permits unrestricted use,
distribution, and reproduction in any medium, provided the
original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the 
                        Creative Commons Attribution License, which permits unrestricted use, distribution, 
                        and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """
                        This is an open access article distributed under the Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This research note is distributed under the  Commons
						Attribution-Noncommercial 3.0 License.""": 'http://creativecommons.org/licenses/by-nc/3.0/',
    """This is an open access article distributed under 
                        the Creative Commons Attribution License, which permits unrestricted use, 
                        distribution, and reproduction in any medium, provided the original work is 
                        properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the Creative Commons Attribution License,
which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This research note is distributed under the  Creative Commons
Attribution 3.0 License.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the Creative Commons Attribution 
                        License, which permits unrestricted use, distribution, and reproduction in any medium, 
                        provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the Creative Commons Attribution License, which
                        permits unrestricted use, distribution, and reproduction in any medium, provided the original work 
                        is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the Creative Commons attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the Creative Commons Attribution License, which
 permits unrestricted use, distribution, and reproduction in any medium, provided the original work 
 is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the Creative Commons Attribution License, which permits unrestricted use,
                                    distribution, and reproduction in any medium, provided the
                                    original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an 
                        open access article distributed under the 
                        Creative Commons Attribution License, 
                        which permits unrestricted use, 
                        distribution, and reproduction in any 
                        medium, provided the original work is 
                        properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This work is subject to copyright. All rights are reserved, whether the whole or part of the material is concerned, specifically the rights of translation, reprinting, reuse of illustrations, recitation, broadcasting, reproduction on microfilm or in any other way, and storage in data banks. Duplication of this publication or parts thereof is permitted only under the provisions of the German Copyright Law of September 9, 1965, in its current version, and permission for use must always be obtained from Springer-Verlag. Violations are liable for prosecution under the German Copyright Law.""": '',
    """This work is subject to copyright. All rights are reserved, whether the whole or part of the material is concerned, specifically the rights of translation, reprinting, reuse of illustrations, recitation, broadcasting, reproduction on microfilm or in any other way, and storage in data banks. Duplication of this publication or parts thereof is permitted only under the provisions of the German Copyright Law of September 9, in its current version, and permission for use must always be obtained from Springer-Verlag. Violations are liable for prosecution under the German Copyright Law.""": '',
    """This is an open access article  distributed under the Creative Commons Attribution License, which  permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly 
cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open-access article distributed under the terms of the Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original author and source are credited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the terms of the Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any  medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the  Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """Thi is an open access article distributed under the terms of the Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the Creative Commons Attribution License, which permits unrestricted
use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
        """This is an Open Access article distributed under the terms of the Creative Commons Attribution licence which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """License information: This is an open-access article distributed under the terms of the Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0',
    """This is an open access article distributed under the terms of the Creative Commons Attribution License ( http://www.creativecommons.org/licenses/by/2.0 ) which permits unrestricted use, distribution and reproduction provided the original work is properly cited.""": 'http://www.creativecommons.org/licenses/by/2.0',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution License (http://creativecommons.org/licenses/by/2.0), which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/2.0',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution License ( http://creativecommons.org/licenses/by/2.0 ), which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/2.0',
    """
                     This article is an open-access article distributed under the terms and conditions of the Creative Commons Attribution license ( http://creativecommons.org/licenses/by/3.0/ ). 
                """: 'http://creativecommons.org/licenses/by/3.0/',
    """§ The authors have paid a fee to allow immediate free access to this article.""": '',  # TODO: Free as in freedom?
    """† The authors have paid a fee to allow immediate free access to this article.""": '',  # TODO ^
    """‡ The authors have paid a fee to allow immediate free access to this article.""": '',  # TODO ^
    """‖ The authors have paid a fee to allow immediate free access to this article.""": '',  # TODO ^
    """‡The authors have paid a fee to allow immediate free access to this article.""": '',  # TODO ^
    """†The authors have paid a fee to allow immediate free access to this article.""": '',  # TODO ^
    """‡ The authors have paid a fee to allow immediate free access to this article""": '',  # TODO ^
    """‖The authors have paid a fee to allow immediate free access to this article.""": '',  # TODO ^
    """The authors have paid a fee to allow immediate free access to this article.""": '',  # TODO ^
    """† The author has paid a fee to allow immediate free access to this article.""": '', # TODO ^
    """Available freely online through the author-supported open access option.""": '',  # TODO ^
    """This is an Open Access article which permits unrestricted noncommercial use,
                    provided the original work is properly cited.""": '',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/3.0/ ), which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/3.0/',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/2.5/uk/ ), which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/2.5/uk/',
    """Readers may use this article as long as the work is properly cited, the use is
						educational and not for profit, and the work is not altered. See  http://creativecommons.org/licenses/by-nc-nd/3.0/  for details.""": 'http://creativecommons.org/licenses/by-nc-nd/3.0/',
    """The online version of this article is published within an Open Access environment subject to the conditions
of the Creative Commons Attribution-NonCommercial-ShareAlike licence
< http://creativecommons.org/licenses/by-nc-sa/2.5/>.  The written permission
of Cambridge University Press must be obtained for commercial re-use""": 'http://creativecommons.org/licenses/by-nc-sa/2.5/',
    """This is an Open Access article distributed under the terms of the Creative
                        Commons Attribution Non-Commercial License
                        ( http://creativecommons.org/licenses/by-nc/2.5 ), which permits unrestricted
                        non-commercial use, distribution, and reproduction in any medium, provided
                        the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/2.5',
    """Users may view, print, copy, download and text and data- mine the content in such documents, for the purposes of academic research, subject always to the full Conditions of use:
 http://www.nature.com/authors/editorial_policies/license.html#terms 
""": 'http://www.nature.com/authors/editorial_policies/license.html#terms',
    """
This is an open access article distributed under the terms of the Creative Commons Attribution License (http://creativecommons.org/licenses/by/2.0), which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.
""": 'http://creativecommons.org/licenses/by/2.0',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/3.0 ), which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/3.0',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/2.0 ), which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/2.0',
    """The online version of this article is published within an Open Access environment subject to the conditions of the Creative Commons Attribution-NonCommercial-ShareAlike licence < http://creativecommons.org/licenses/by-nc-sa/2.5/>.  The written permission of Cambridge University Press must be obtained for commercial re-use.""": 'http://creativecommons.org/licenses/by-nc-sa/2.5/',
    """The online version of this article has been published under an open access model, users are entitle to use, reproduce, disseminate, or display the open access version of this article for non-commercial purposes provided that: the original authorship is properly and fully attributed; the Journal and the European Society for Medical Oncology are attributed as the original place of publication with the correct citation details given; if an article is subsequently reproduced or disseminated not in its entirety but only in part or as a derivative work this must be clearly indicated. For commercial re-use, please contact journals.permissions@oxfordjournals.org""": '',
    """The online version of this article has been published under an open access model. users are entitle to use, reproduce, disseminate, or display the open access version of this article for non-commercial purposes provided that: the original authorship is properly and fully attributed; the Journal and the European Society for Medical Oncology are attributed as the original place of publication with the correct citation details given; if an article is subsequently reproduced or disseminated not in its entirety but only in part or as a derivative work this must be clearly indicated. For commercial re-use, please contact journals.permissions@oxfordjournals.org""": '',
    """The online version of this article has been published under an open access model. Users are entitled to use, reproduce, disseminate, or display the open access version of this article for non-commercial purposes provided that: the original authorship is properly and fully attributed; the Journal and Oxford University Press are attributed as the original place of publication with the correct citation details given; if an article is subsequently reproduced or disseminated not in its entirety but only in part or as a derivative work this must be clearly indicated. For commercial re-use, please contact journals.permissions@oxfordjournals.org.""": '',
    """The online version of this article has been published under an open access model. Users are entitled to use, reproduce, disseminate, or display the open access version of this article for non-commercial purposes provided that: the original authorship is properly and fully attributed; the Journal and Oxford University Press are attributed as the original place of publication with the correct citation details given; if an article is subsequently reproduced or disseminated not in its entirety but only in part or as a derivative work this must be clearly indicated. For commercial re-use, please contact journals.permissions@oxfordjournals.org""": '',
    """creative commons""": '',  # WTF
    """Open Access""": '',  # The more you know!
    """This is a free access article, distributed under terms ( http://www.nutrition.org/publications/guidelines-and-policies/license/ ) which permit unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://www.nutrition.org/publications/guidelines-and-policies/license/',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses?by-nc/2.5 ), which permits unrestricted non-commercial use distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses?by-nc/2.5',
    """This is an open access article. Unrestricted non-commercial use is permitted provided the original work is properly cited.""": '',
    """Readers may use this article aslong as long as the work is properly cited, the use is educational and not for profit, and the work is not altered. See  http://creativecommons.org/licenses/by-nc-nd/3.0/  for details.""": 'http://creativecommons.org/licenses/by-nc-nd/3.0/',
    """Readers may use this article as long as the work is properly cited, the use is educational and not for profit, and the work is not altered. See  http://creativecommons.org/licenses/by-nc-nd/3.0/ for details.""": 'http://creativecommons.org/licenses/by-nc-nd/3.0/',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/2.5/ ) which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/2.5/',
    """Freely available online through the  American Journal of Tropical Medicine and Hygiene  Open Access option.""": '',
    """This is a free access article, distributed under terms that permit unrestricted noncommercial use, distribution, and reproduction in any medium, provided the original work is properly cited.  http://www.nutrition.org/publications/guidelines-and-policies/license/ .""": 'http://www.nutrition.org/publications/guidelines-and-policies/license/',
    """
This article, manuscript, or document is copyrighted by the American 
Psychological Association (APA). For non-commercial, education 
and research purposes, users may access, download, copy, display, 
and redistribute this article or manuscript as well as adapt, translate, 
or data and text mine the content contained in this document. 
For any such use of this document, appropriate attribution 
or bibliographic citation must be given. Users should not delete 
any copyright notices or disclaimers. For more information or to 
obtain permission beyond that granted here, visit 
http://www.apa.org/about/copyright.html.
""": 'http://www.apa.org/about/copyright.html',
    """This article, manuscript, or document is copyrighted by the American Psychological Association (APA). For non-commercial, education and research purposes, users may access, download, copy, display, and redistribute this article or manuscript as well as adapt, translate, or data and text mine the content contained in this document. For any such use of this document, appropriate attribution or bibliographic citation must be given. Users should not delete any copyright notices or disclaimers. For more information or to obtain permission beyond that granted here, visit http://www.apa.org/about/copyright.html.""": 'http://www.apa.org/about/copyright.html',
    """Readers may use this article as long as the work is properly cited, the use is educational and not for profit, and the work is not altered. See  http://creativecommons.org/licenses/by-nc-nd/3.0/  for details.""": 'http://creativecommons.org/licenses/by-nc-nd/3.0/',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial Share Alike License ( http://creativecommons.org/licenses/by-nc-sa/3.0 ), which permits unrestricted non-commercial use, distribution and reproduction in any medium provided that the original work is properly cited and all further distributions of the work or adaptation are subject to the same Creative Commons License terms""": 'http://creativecommons.org/licenses/by-nc-sa/3.0',
    """Readers may use this article as long as the work is properly cited, the use is educational and not for profit, and the work is not altered. See  http://creativecommons.org/licenses/by	-nc-nd/3.0/  for details.""": 'http://creativecommons.org/licenses/by-nc-nd/3.0/',
    """This is an open access article distributed under the Creative Commons 
                        Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """Readers may use this article as long as the work is properly cited, the use is
                    educational and not for profit, and the work is not altered. See  http://creativecommons.org/licenses/by-nc-nd/3.0/  for
                    details.""": 'http://creativecommons.org/licenses/by-nc-nd/3.0/',
    """This is an open access article distributed under the Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited. """: 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under theCreative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/3.0/us/ ) which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/3.0/us/',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution License ( http://creativecommons.org/licenses/by/3.0 ), which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0',
    """This is an Open Access article which permits unrestricted noncommercial use, provided the original work is properly cited. Clinical Ophthalmology 2011:5 101–108""": '',
    """This is an Open Access article distributed under the terms and of the American Society of Tropical Medicine and Hygiene's Re-use License which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": '',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/2.5/ ), which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/2.5/',
    """This document may be redistributed and reused, subject to  www.the-aps.org/publications/journals/funding_addendum_policy.htm .""": 'http://www.the-aps.org/publications/journals/funding_addendum_policy.htm',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution-Noncommercial License ( http://creativecommons.org/licenses/by-nc/3.0/ ), which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited. Information for commercial entities is available online ( http://www.chestpubs.org/site/misc/reprints.xhtml ).""": 'http://creativecommons.org/licenses/by-nc/3.0/',
    """This article is an open-access article distributed under the terms and conditions of the Creative Commons Attribution license ( http://creativecommons.org/licenses/by/3.0/ ).""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an open access article distributed under the terms of
            the Creative Commons Attribution License (http://creativecommons.org/licenses/by/2.0),
            which permits unrestricted use, distribution, and reproduction in any medium, provided
            the original work is properly cited. """: 'http://creativecommons.org/licenses/by/2.0',
    """Readers may use this article as long as the work is properly cited, the use is educational and not for profit,and the work is not altered. See  http://creativecommons.org/licenses/by-nc-nd/3.0/  for details.""": 'http://creativecommons.org/licenses/by-nc-nd/3.0/',
    """This is an open access article 
                        distributed under the Creative Commons Attribution License, which permits 
                        unrestricted use, distribution, and reproduction in any medium, provided the 
                        original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/2.0/uk/ ), which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/2.0/uk/',
    """This is an Open Access article distributed under the terms of the American Society of Tropical Medicine and Hygiene's Re-use License which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": '',
    """This is an open access article distributed under the Creative Commons Attribution License, which permits unrestricted use, distribution and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/2.0/ ) which permits unrestricted non-commercial use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/2.0/',
    """This is an open access article distributed under the Creative Commons Attribution License, which permits unrestricted use, distribution, and
reproduction in any medium, provided the original work is properly
cited.""": 'http://creativecommons.org/licenses/by/3.0/',
    """This is an Open Access article: verbatim copying and redistribution of this article are permitted in all media for any purpose""": 'data:text/plain,This%20is%20an%20Open%20Access%20article%3A%20verbatim%20copying%20and%20redistribution%20of%20this%20article%20are%20permitted%20in%20all%20media%20for%20any%20purpose',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution Non-Commercial Share Alike License ( http://creativecommons.org/licenses/by-nc-sa/3.0 ), which permits unrestricted non-commercial use, distribution and reproduction in any medium provided that the original work is properly cited and all further distributions of the work or adaptation are subject to the same Creative Commons License terms.""": 'http://creativecommons.org/licenses/by-nc-sa/3.0',
    """This is an Open Access article distributed under the terms of the Creative Commons Attribution License (http://creativecommons.org/licenses/by/2.0), which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.
""": 'http://creativecommons.org/licenses/by/2.0',
    """This is an Open Access article distributed under the terms of the Creative Commons
Attribution Non-Commercial License ( http://creativecommons.org/licenses/by-nc/2.5 ),
which permits unrestricted non-commercial use, distribution, and reproduction in any
medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by-nc/2.5',
    """This is an open access article distributed under the terms of the Creative Commons Attribution License (<url>http://creativecommons.org/licenses/by/2.0</url>), which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/2.0',
    """This article is in the public domain.""": 'http://creativecommons.org/licenses/publicdomain/',
    """Distributed under the Hogrefe OpenMind License [
http://dx.doi.org/10.1027/a000001]""": 'http://dx.doi.org/10.1027/a000001',
    """This is an open access article distributed under the Creative Commons Attribution License, in which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0',
    """This is an open access article distributed under the terms of the Creative Commons Attribution License (http://creativecommons.org/licenses/by/2.0), which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/2.0',
    """This is an open access paper distributed under the Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/3.0',
    """This is an open access article distributed under the terms of the Creative Commons Attribution License ( http://creativecommons.org/licenses/by/2.0 ), which permits unrestricted use, distribution, and reproduction in any medium, provided the original work is properly cited.""": 'http://creativecommons.org/licenses/by/2.0',
}

def _get_article_license_url(tree):
    """
    Given an ElementTree, returns article license URL.
    """
    license = ElementTree(tree).find('front/article-meta/permissions/license')
    try:
        return license.attrib['{http://www.w3.org/1999/xlink}href']
    except AttributeError:  # license statement is missing
        return ''
    except KeyError:  # license statement is in plain text
        license_text = ' '.join(license.itertext()).encode('utf-8')
        if license_text in license_url_equivalents:
            return license_url_equivalents[license_text]
        else:
            # FIXME: revert this to an exception some time in the future
            filename = '/tmp/pmc-' + md5(license_text).hexdigest()
            with open(filename, 'w') as f:
                f.write(license_text)
                stderr.write("Unknown license statement:\n%s\n" % \
                    str(license_text))

def _get_article_copyright_holder(tree):
    """
    Given an ElementTree, returns article copyright holder.
    """
    copyright_holder = ElementTree(tree).find(
        'front/article-meta/permissions/copyright-holder'
    )
    try:
        return copyright_holder.text
    except AttributeError:  # no copyright_holder known
        return ''

from sys import stderr

def _get_supplementary_materials(tree):
    """
    Given an ElementTree, returns a list of article supplementary materials.
    """
    materials = []
    for xref in tree.iter('xref'):
        try:
            if xref.attrib['ref-type'] == 'supplementary-material':
                rid = xref.attrib['rid']
                sup = _get_supplementary_material(tree, rid)
                if sup:
                    materials.append(sup)
        except KeyError:  # xref is missing ref-type or rid
            pass
    return materials

def _get_supplementary_material(tree, rid):
    """
    Given an ElementTree and an rid, returns supplementary material as a dictionary
    containing url, mimetype and label and caption.
    """
    for sup in tree.iter('supplementary-material'):
        try:
            if sup.attrib['id'] == rid:  # supplementary material found
                result = {}
                sup_tree = ElementTree(sup)

                label = sup_tree.find('label')
                result['label'] = ''
                if label is not None:
                    result['label'] = label.text

                caption = sup_tree.find('caption')
                result['caption'] = ''
                if caption is not None:
                    result['caption'] = ' '.join(caption.itertext())

                media = sup_tree.find('media')
                if media is not None:
                    result['mimetype'] = media.attrib['mimetype']
                    result['mime-subtype'] = media.attrib['mime-subtype']
                    result['url'] = _get_supplementary_material_url(
                        _get_pmcid(tree),
                        media.attrib['{http://www.w3.org/1999/xlink}href']
                    )
                    return result
        except KeyError:  # supplementary material has no ID
            continue

def _get_pmcid(tree):
    """
    Given an ElementTree, returns PubMed Central ID.
    """
    front = ElementTree(tree).find('front')
    for article_id in front.iter('article-id'):
        if article_id.attrib['pub-id-type'] == 'pmc':
            return article_id.text

def _get_supplementary_material_url(pmcid, href):
    """
    This function creates absolute URIs for supplementary materials,
    using a PubMed Central ID and a relative URI.
    """
    return str('http://www.ncbi.nlm.nih.gov/pmc/articles/PMC' + pmcid +
        '/bin/' + href)
