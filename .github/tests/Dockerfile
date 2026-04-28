FROM catthehacker/ubuntu:act-latest

# Install gh CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
      https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update -qq && apt-get install -y gh

# Move real binaries aside and install wrappers
RUN mv /usr/bin/git /usr/bin/git.real && \
    mv "$(which gh)" /usr/local/bin/gh.real

COPY wrappers/git /usr/local/bin/git
COPY wrappers/gh  /usr/local/bin/gh
RUN chmod +x /usr/local/bin/git /usr/local/bin/gh
