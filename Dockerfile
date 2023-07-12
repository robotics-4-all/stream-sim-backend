FROM python:3.7

COPY ./ ./app
WORKDIR ./app
# COPY ./commlib-py /commlib
RUN pip install -r requirements.txt

RUN cd ./derp-me && pip install .
RUN cd ./commlib-py && pip install .

RUN pip install .

WORKDIR  ./bin
# CMD ["python", "main_remote.py"]
CMD ["bash", "-c", "python main_remote.py"]
