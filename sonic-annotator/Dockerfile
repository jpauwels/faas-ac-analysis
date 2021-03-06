FROM jpauwels/vamp-plugins:v18.06

# 1. Use any image as your base image, or "scratch"
# 2. Add fwatchdog binary via https://github.com/openfaas/faas/releases/
# 3. Then set fprocess to the process you want to invoke per request - i.e. "cat" or "my_binary"

# Add watchdog
RUN apt-get update -y \
&&  apt-get install -y curl \
&& curl -sSL https://github.com/openfaas/faas/releases/download/0.9.6/fwatchdog > /usr/bin/fwatchdog \
&& chmod +x /usr/bin/fwatchdog \
&& apt-get autoremove --purge -y curl \
&&  apt-get clean \
&&  rm -rf /var/lib/apt/lists/*

# Add non root user
RUN addgroup --system app && adduser --system --ingroup app app
RUN chown app /home/app
WORKDIR /home/app
USER app

COPY transforms transforms
COPY entrypoint.sh entrypoint.sh
WORKDIR /tmp

# Populate example here - i.e. "cat", "sha512sum" or "node index.js"
ENV fprocess="/home/app/entrypoint.sh"
HEALTHCHECK --interval=5s CMD [ -e /tmp/.lock ] || exit 1
CMD [ "fwatchdog" ]
