from distutils.core import setup
setup(
      name = 'reddit-download',
      version = '0.1-dev',
      url = 'https://github.com/whatevsz/reddit-download',

      author = 'Hannes Körber',
      author_email = 'hannes.koerber@gmail.com',
      maintainer = 'Hannes Körber',
      maintainer_email = 'hannes.koerber@gmail.com',

      license = 'GNU GPL',
      platforms = ['Linux'],
      description = 'A script to download images on reddit',
      long_description = open('README').read(),

      package_dir = {'reddit-download': 'src'},
      packages = ['reddit-download', 'reddit-download.RedditImageGrab'],
      scripts = [],
      data_files = [],
      requires = [],

      classifiers = [
          'Development Status ::3 - Alpha',
          'Environment :: Console',
          'Intended Audience :: End Users/Desktop',
          'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
          'Natural Language :: English',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python :: 3.3',
          'Topic :: System :: Internet'
          ]
      )
