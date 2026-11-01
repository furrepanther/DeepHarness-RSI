"""Small host-neutral launcher-mode helper used by the review wrapper.

The wrapper must be runnable from a personal fork on either runner host. This
module permits only local-router execution; cloud-required handoffs are
returned to the parent rather than dispatched directly by a review worker.
"""

import os


INFERENCE_MODE_ENV = "PRIMUS_INFERENCE_MODE"


def validate_inference_mode(mode):
    if mode != "local":
        raise ValueError(f"{INFERENCE_MODE_ENV} must be local for review workers; handle cloud-required signals through the router handoff")
    return mode


def add_inference_mode(parser):
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "-c",
        "--cloud",
        dest="inference_mode",
        action="store_const",
        const="cloud",
        help="unsupported: cloud-required results are handed to the parent",
    )
    modes.add_argument(
        "-l",
        "--local",
        dest="inference_mode",
        action="store_const",
        const="local",
        help="use local inference only; fail without cloud fallback",
    )
    parser.set_defaults(inference_mode=None)


def parse_inference_args(parser, argv=None):
    """Explicit CLI > inherited environment > local; export only after validation."""
    args = parser.parse_args(argv)
    mode = args.inference_mode
    if mode is None:
        mode = os.environ.get(INFERENCE_MODE_ENV, "local")
    try:
        args.inference_mode = validate_inference_mode(mode)
    except ValueError as exc:
        parser.error(str(exc))
    os.environ[INFERENCE_MODE_ENV] = args.inference_mode
    return args


def child_mode_args(args):
    return ["--" + validate_inference_mode(args.inference_mode)]
