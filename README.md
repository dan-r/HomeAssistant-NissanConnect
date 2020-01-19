# kamereon-python

Kamereon is platform used for connected cars from the Renault-Nissan-Mitsubishi Alliance from 2019 onwards.

## Compatible models

Theoretically...

* Nissan Navara (from July 2019)
* Nissan Leaf (from May 2019)
* Nissan Juke (from November 2019)
* Renault Zoe?

## Example usage

    pip install -r requirements.txt
    python kamereon/__init__.py EU my-email-login@foo.bar my-password

## This project

Is a proof-of-concept, and my goal is to build this into a general library for this platform, and use that to build a [Home Assistant](https://www.home-assistant.io/) component.

### License

Apache 2

## References

This wouldn't have been half as easy to put together if it wasn't for the work by [Tobias Westergaard Kjeldsen](https://gitlab.com/tobiaswkjeldsen) on reverse engineering Nissan Connect Services apps for his [dartnissanconnect](https://gitlab.com/tobiaswkjeldsen/dartnissanconnect) library and [My Leaf app](https://gitlab.com/tobiaswkjeldsen/carwingsflutter)