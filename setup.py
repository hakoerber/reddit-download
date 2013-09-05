from distutils.core import setup

setup(
      name = 'reddit-download',
      version = '0.1',
      url = 'http://github.com/whatevsz/reddit-download',
      download_url = 'http://github.com/whatevsz/reddit-download/releases',

      author = 'Hannes Körber',
      author_email = 'hannes.koerber@gmail.com',
      maintainer = 'Hannes Körber',
      maintainer_email = 'hannes.koerber@gmail.com',

      license = 'GNU GPL',
      platforms = ['Linux'],
      description = 'A downloader for images from reddit.',
      long_description = open('README.rst').read(),

      package_dir = {'reddit-download': 'src'},
      packages = ['reddit-download', 'reddit-download.RedditImageGrab'],
      scripts = [],
      data_files = [],
      requires = ['requests'],

      classifiers = [
          'Development Status :: 2 - Pre-Alpha',
          'Environment :: Console',
          'Intended Audience :: End Users/Desktop',
          'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
          'Natural Language :: English',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.3',
          'Topic :: Internet',
          'Topic :: Multimedia :: Graphics'
          ],
      keywords = "reddit image imgur download"
      )
