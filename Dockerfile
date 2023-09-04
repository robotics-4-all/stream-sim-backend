FROM python:3.7

COPY ./derp-me /derp-me
COPY ./commlib-py /commlib-py
COPY ./robot_motion /robot_motion

RUN cd /derp-me && pip install .
RUN cd /commlib-py && pip install .
RUN cd /robot_motion && pip install .

COPY ./requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

COPY ./ /app

WORKDIR /app

RUN python setup.py develop

WORKDIR /app/bin

RUN apt update -y && apt install -y build-essential libasound2-dev
RUN pip install pyalsaaudio

# CMD ["python", "main_remote.py"]
CMD ["python", "main_remote.py"]
