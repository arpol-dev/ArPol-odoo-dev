{
    "name": "Website Image Zoom",
    "summary": """Website Image Zoom""",
    "version": "16.0.1.0.1",
    "category": "Website",
    "images": ["static/description/banner.png"],
    "author": "UnitSoft",
    "website": "https://unitsoft.com.ua/",
    "depends": ["website"],
    "data": [
        "views/snippets.xml",
     ],
    "assets": {
        "web.assets_frontend": [
            "us_website_image_zoom/static/src/scss/website_image.scss",
            "us_website_image_zoom/static/src/scss/website_viewer_frontend.scss",
            "us_website_image_zoom/static/src/xml/us_website_image_viewer.xml",
            "us_website_image_zoom/static/src/js/components/website_image_viewer.js",
            "us_website_image_zoom/static/src/js/website_image_zoom.js",
        ],
    },
    "application": False,
    "license": "LGPL-3",
    "installable": True,
    "active": True,
}